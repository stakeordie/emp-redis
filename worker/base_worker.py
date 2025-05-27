#!/usr/bin/env python3
# Base worker for the EmProps Redis Worker
import os
import sys
import asyncio
import json
import uuid
import time  # [2025-05-26T20:45:00-04:00] Added missing time import
import websockets
from typing import Dict, List, Any, Optional, Union, cast, TypeVar, Generic
from enum import Enum, auto
from dotenv import load_dotenv

# [2025-05-25T21:45:00-04:00] Updated import path to match actual deployment package structure
# The deployment environment has message_models.py in core/ not in core/core_types/
from core.message_models import (
    UpdateJobProgressMessage,
    FailJobMessage,
    WorkerStatusMessage,
    RegisterWorkerMessage
)



# Add the parent directory to the Python path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

# Add the current directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Import logger first for proper diagnostics
from core.utils.logger import logger

# Import required modules using package structure
# This leverages the __init__.py files for proper package imports
ConnectorInterface = None
load_connectors = None
get_worker_capabilities = None

# Try different import approaches in sequence
import_success = False

# Approach 1: Try importing from worker package (best practice)
try:
    logger.debug("[base_worker.py] Attempting to import from worker package")
    from worker import ConnectorInterface as WorkerConnectorInterface
    from worker import load_connectors as worker_load_connectors
    from worker import get_worker_capabilities as worker_get_capabilities
    
    ConnectorInterface = WorkerConnectorInterface
    load_connectors = worker_load_connectors
    get_worker_capabilities = worker_get_capabilities
    
    logger.debug("[base_worker.py] Successfully imported from worker package")
    import_success = True
except ImportError as e:
    logger.debug(f"[base_worker.py] Failed to import from worker package: {str(e)}")

# Approach 2: Try direct imports (for Docker container)
if not import_success:
    try:
        logger.debug("[base_worker.py] Attempting direct imports")
        from connector_interface import ConnectorInterface as DirectConnectorInterface
        from connector_loader import load_connectors as direct_load_connectors
        from connector_loader import get_worker_capabilities as direct_get_capabilities
        
        ConnectorInterface = DirectConnectorInterface
        load_connectors = direct_load_connectors
        get_worker_capabilities = direct_get_capabilities
        
        logger.debug("[base_worker.py] Successfully imported directly")
        import_success = True
    except ImportError as e2:
        logger.debug(f"[base_worker.py] Failed direct imports: {str(e2)}")

# Approach 3: Try emp-redis-worker specific imports (for new Docker structure)
if not import_success:
    try:
        logger.debug("[base_worker.py] Attempting emp-redis-worker specific imports")
        from emp_redis_worker.worker import ConnectorInterface as EmpConnectorInterface
        from emp_redis_worker.worker import load_connectors as emp_load_connectors
        from emp_redis_worker.worker import get_worker_capabilities as emp_get_capabilities
        
        ConnectorInterface = EmpConnectorInterface
        load_connectors = emp_load_connectors
        get_worker_capabilities = emp_get_capabilities
        
        logger.debug("[base_worker.py] Successfully imported from emp_redis_worker.worker")
        import_success = True
    except ImportError as e3:
        logger.debug(f"[base_worker.py] Failed emp-redis-worker imports: {str(e3)}")

# Check if any import approach succeeded
if not import_success:
    error_msg = "Failed to import required modules using any approach"
    logger.error(f"[base_worker.py] {error_msg}")
    raise ImportError(error_msg)

from core.message_models import (
    MessageType,
    WorkerHeartbeatMessage,
    WorkerStatusMessage,
    CompleteJobMessage,
    BaseMessage,
    ClaimJobMessage,
    JobAvailableMessage,
    UpdateJobProgressMessage,
    MessageModels,
    RegisterWorkerMessage,
    FailJobMessage  # Added: 2025-04-17T15:12:00-04:00 - For properly reporting failed jobs
)

class WorkerStatus(Enum):
    """Worker status enum"""
    IDLE = auto()
    BUSY = auto()
    ERROR = auto()

class BaseWorker:
    """Base worker class for the EmProps Redis Worker"""
    
    def __init__(self):
        """Synchronous initialization of base worker"""
        # Load worker-specific variables (WORKER_ID, WORKER_COMFYUI_PORT) from .env
        load_dotenv() # Load .env file into environment
        
        # Generate worker ID with the format worker-gpu0-<UUID>
        # AI-generated fix: 2025-04-04T21:37:21 - Updated worker ID format
        import uuid
        worker_base = os.environ.get("WORKER_BASE_ID", "worker-gpu0")
        worker_uuid = str(uuid.uuid4())
        self.worker_id = f"{worker_base}-{worker_uuid}"
        # Note: WORKER_COMFYUI_PORT is loaded into env, but might be used by connectors later
        
        # Log the worker ID for debugging
        print(f"Initializing worker with ID: {self.worker_id} (loaded via dotenv)")
        
        # [2025-05-26T19:07:00-04:00] Added storage for chunked messages
        # This dictionary will store partial chunks until all chunks of a message are received
        # Format: {message_id: {"chunks": {chunk_id: chunk_data}, "total_chunks": N, "message_hash": hash, "original_type": type, "job_id": job_id, "received_at": timestamp}}
        self.chunked_messages = {}

        # Load GLOBAL settings directly from environment (set by container)
        # Support both namespaced (WORKER_*) and non-namespaced versions for backward compatibility
        self.auth_token = os.environ.get("WORKER_WEBSOCKET_AUTH_TOKEN", os.environ.get("WEBSOCKET_AUTH_TOKEN", ""))
        self.heartbeat_interval = int(os.environ.get("WORKER_HEARTBEAT_INTERVAL", os.environ.get("HEARTBEAT_INTERVAL", "20")))
        self.use_ssl = os.environ.get("WORKER_USE_SSL", os.environ.get("USE_SSL", "false")).lower() in ("true", "1", "yes")
        
        # Log the environment variables we're using
        print(f"[base_worker.py] Using environment variables:")
        print(f"[base_worker.py] WORKER_ID: {self.worker_id}")
        print(f"[base_worker.py] WORKER_USE_SSL: {self.use_ssl}")
        print(f"[base_worker.py] WORKER_HEARTBEAT_INTERVAL: {self.heartbeat_interval}")
        
        # Construct WebSocket URL using global settings + loaded WORKER_ID
        direct_ws_url = os.environ.get("WORKER_REDIS_WS_URL", os.environ.get("REDIS_WS_URL", ""))

        if direct_ws_url:
            base_url = direct_ws_url
            self.redis_host = "Using WORKER_REDIS_WS_URL directly"
            self.redis_port = ""
        else:
            # Try both namespaced and non-namespaced versions
            self.redis_host = os.environ.get("WORKER_REDIS_API_HOST", os.environ.get("REDIS_API_HOST", "localhost"))
            self.redis_port = os.environ.get("WORKER_REDIS_API_PORT", os.environ.get("REDIS_API_PORT", ""))
            
            print(f"[base_worker.py] WORKER_REDIS_API_HOST: {self.redis_host}")
            print(f"[base_worker.py] WORKER_REDIS_API_PORT: {self.redis_port}")

            protocol = "wss" if self.use_ssl else "ws"
            if self.redis_port:
                base_url = f"{protocol}://{self.redis_host}:{self.redis_port}/ws/worker/{self.worker_id}"
            else:
                base_url = f"{protocol}://{self.redis_host}/ws/worker/{self.worker_id}"

        self.redis_ws_url = f"{base_url}?token={self.auth_token}" if self.auth_token else base_url
        
        # Initialize MessageModels for message parsing
        self.message_models = MessageModels()
        
        # Placeholders for async-loaded attributes
        self.connectors = None
        self.capabilities = None
        
        # Worker state
        self.status = WorkerStatus.IDLE
        self.current_job_id = None

    async def async_init(self):
        """Asynchronous initialization of worker components"""
        # [2025-05-25T18:10:00-04:00] Added null checks to prevent "None not callable" errors
        # Check if load_connectors is callable
        if load_connectors is None or not callable(load_connectors):
            error_msg = f"load_connectors is not callable: {type(load_connectors)}"
            logger.error(f"[base_worker.py async_init()] {error_msg}")
            raise TypeError(error_msg)
            
        # Load connectors
        self.connectors = await load_connectors()   # Load connectors           
        
        # Initialize connectors
        logger.debug(f"[base_worker.py async_init()] Initializing connectors...{self.connectors}")
        
        # Check if get_worker_capabilities is callable
        if get_worker_capabilities is None or not callable(get_worker_capabilities):
            error_msg = f"get_worker_capabilities is not callable: {type(get_worker_capabilities)}"
            logger.error(f"[base_worker.py async_init()] {error_msg}")
            raise TypeError(error_msg)
            
        # Worker capabilities
        self.capabilities = await get_worker_capabilities(self.connectors)
        
        logger.debug(f"[base_worker.py async_init()] Worker capabilities: {self.capabilities}")
        
        return self
    
    def get_connector_statuses(self) -> Dict[str, Any]:
        """Get connection status for all connectors
        
        Returns:
            Dict[str, Any]: Dictionary of connector statuses
        """
        connector_statuses: Dict[str, Any] = {}
        # Iterate over items (job_type, connector) instead of just keys
        if self.connectors is None:
            return connector_statuses
        for job_type, connector in self.connectors.items():
            try:
                status = connector.get_connection_status()
                connector_statuses[status["service"]] = status
            except Exception as e:
                logger.error(f"[base_worker.py get_connector_statuses()]: Error getting connection status for connector: {str(e)}")
                # Add error status for this connector
                connector_statuses[job_type] = {
                    "connected": False,
                    "service": job_type,
                    "details": {"error": str(e)}
                }
        return connector_statuses
    
    async def send_status_update(self, websocket):
        """Send worker status update to Redis Hub
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
        """
        try:
            # Get connection status for all connectors
            connector_statuses: Dict[str, Any] = self.get_connector_statuses()
            
            # Create worker status message using WorkerStatusMessage class
            capabilities_dict = self.capabilities or {}  # Use empty dict if None
            status_message = WorkerStatusMessage(
                worker_id=self.worker_id,
                status=self.status.name.lower(),
                capabilities={
                    **capabilities_dict,
                    "connector_statuses": connector_statuses
                }
            )
            
            # Send status message
            await websocket.send(status_message.model_dump_json())
            logger.debug(f"[base_worker.py send_status_update()]: Sent status update with connector statuses")
        except Exception as e:
            logger.error(f"[base_worker.py send_status_update()]: Error sending status update: {str(e)}")
    
    async def send_heartbeat(self, websocket):
        """Send heartbeat messages to keep the connection alive
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
        """
        try:
            print(f"[PRINT] Starting heartbeat for worker {self.worker_id}")  # Direct print
            status_interval = 5  # Send full status every 5 heartbeats
            counter = 0
            while True:
                try:
                    # Increment counter
                    counter += 1
                    # Every status_interval heartbeats, send a full status update
                    if counter % status_interval == 0:
                        await self.send_status_update(websocket)
                    
                    # Create heartbeat message using WorkerHeartbeatMessage class
                    heartbeat_message = WorkerHeartbeatMessage(
                        worker_id=self.worker_id,
                        status=self.status.name.lower(),
                        load=0.0
                    )
                    # Send heartbeat message
                    await websocket.send(heartbeat_message.model_dump_json())
                    # Wait for next heartbeat
                    await asyncio.sleep(self.heartbeat_interval)
                except Exception as e:
                    logger.error(f"[base_worker.py send_heartbeat()]: Error sending heartbeat: {str(e)}")
                    await asyncio.sleep(5)  # Wait before retrying
        except Exception as e:
            logger.error(f"[base_worker.py send_heartbeat()]: Fatal error for worker {self.worker_id}: {str(e)}")
    
    async def send_job_failed(self, websocket, job_id, error_message):
        """Send job failed message to the Redis Hub
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
            job_id: The job ID
            error_message: The error message
        """
        # [2025-05-25T21:10:00-04:00] Added missing send_job_failed method to fix type errors
        try:
            # Create job failed message using FailJobMessage class
            job_failed_message = FailJobMessage(
                job_id=job_id,
                worker_id=self.worker_id,
                error=error_message
            )
            
            # Send the message
            await websocket.send(job_failed_message.model_dump_json())
            logger.error(f"[2025-05-25T21:10:00-04:00] Sent job failed message for job {job_id}: {error_message}")
            
            # Also send a final progress update with error status
            await self.send_progress_update(
                websocket, job_id, 0, "error", error_message
            )
        except Exception as e:
            logger.error(f"[2025-05-25T21:10:00-04:00] Error sending job failed message: {str(e)}")
    
    async def send_progress_update(self, websocket, job_id, progress, status, message, connector_details=None):
        """Send progress update for a job
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
            job_id: The job ID
            progress: The progress value (0-100)
            status: The status string (started, running, completed, error)
            message: The status message
            connector_details: Optional details from the connector
        """
        try:
            # Get connector details if available
            connector_details = None
            if self.current_job_id == job_id and self.connectors is not None:
                # Find the active connector for this job
                active_job_type = None
                for job_type, connector in self.connectors.items():
                    if connector.is_processing_job(job_id):
                        active_job_type = job_type
                        break
                
                if active_job_type and active_job_type in self.connectors:
                    # Get the connector instance
                    connectors_dict = dict(self.connectors)
                    connector = connectors_dict[active_job_type]
                    connector_details = connector.get_connection_status()
                    
                    # Add additional debug info
                    if connector_details:
                        connector_details["job_id"] = job_id
                        connector_details["progress_type"] = "heartbeat" if progress == -1 else "normal"
            
            # Create progress update message using UpdateJobProgressMessage class
            progress_message = UpdateJobProgressMessage(
                job_id=job_id,
                worker_id=self.worker_id,
                progress=progress,
                status=status,
                message=message,
                connector_details=connector_details
            )
            
            # [2025-05-23T09:01:28-04:00] Added message size logging to debug WebSocket size issues
            message_json = progress_message.model_dump_json()
            message_size = len(message_json)
            
            # Log message size if it's large
            if message_size > 100000:  # Log messages larger than ~100KB
                logger.warning(f"[base_worker.py send_progress_update()] Large message detected: {message_size} bytes for job {job_id}, status: {status}")
                
                # If it's really large, log more details to help debugging
                if message_size > 500000:  # ~500KB
                    logger.error(f"[base_worker.py send_progress_update()] Very large message: {message_size} bytes for job {job_id}")
                    
                    # Log message structure without the full content
                    message_dict = progress_message.model_dump()
                    if 'connector_details' in message_dict and message_dict['connector_details']:
                        connector_details_size = len(str(message_dict['connector_details']))
                        logger.error(f"[base_worker.py send_progress_update()] Connector details size: {connector_details_size} bytes")
                        # Sample the beginning of connector_details to see what's in there
                        connector_str = str(message_dict['connector_details'])
                        logger.error(f"[base_worker.py send_progress_update()] Connector details sample: {connector_str[:500]}...")
            
            # Send the progress update
            await websocket.send(message_json)            
        except Exception as e:
            logger.error(f"[base_worker.py send_progress_update()]: Error sending progress update for job {job_id}: {str(e)}")
            # [2025-05-23T09:01:28-04:00] Added exception details for WebSocket errors
            import traceback
            logger.error(f"[base_worker.py send_progress_update()]: Stack trace: {traceback.format_exc()}")
    
    # [2025-05-26T19:08:00-04:00] Added methods to handle chunked messages
    def _cleanup_stale_chunks(self):
        """Clean up stale chunked messages that haven't been completed
        
        This method removes any chunked messages that have been partially received
        but haven't been completed within a timeout period (5 minutes).
        """
        now = time.time()
        stale_message_ids = []
        
        # Find stale messages (older than 5 minutes)
        for message_id, message_data in self.chunked_messages.items():
            received_at = message_data.get("received_at", 0)
            if now - received_at > 300:  # 5 minutes timeout
                stale_message_ids.append(message_id)
        
        # Remove stale messages
        for message_id in stale_message_ids:
            logger.warning(f"[2025-05-26T19:08:00-04:00] [base_worker.py] Removing stale chunked message {message_id}")
            del self.chunked_messages[message_id]
            
        if stale_message_ids:
            logger.info(f"[2025-05-26T19:08:00-04:00] [base_worker.py] Cleaned up {len(stale_message_ids)} stale chunked messages")
    
    async def _periodic_chunk_cleanup(self):
        """Run the stale chunk cleanup periodically
        
        This method runs in the background and periodically cleans up stale chunked messages.
        """
        while True:
            try:
                self._cleanup_stale_chunks()
            except Exception as e:
                logger.error(f"[2025-05-26T19:08:00-04:00] [base_worker.py] Error in chunk cleanup: {str(e)}")
            
            # Run cleanup every minute
            await asyncio.sleep(60)
    
    async def _handle_chunked_message(self, websocket, chunk_data):
        """Handle a chunked message from the Redis Hub
        
        This method processes individual chunks of a large message, stores them,
        and reassembles the complete message when all chunks have been received.
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
            chunk_data: The chunk data as a dictionary
        """
        try:
            # Extract chunk metadata
            chunk_id = chunk_data.get("chunk_id")
            total_chunks = chunk_data.get("total_chunks")
            message_id = chunk_data.get("message_id")
            message_hash = chunk_data.get("message_hash")
            original_type = chunk_data.get("original_type")
            job_id = chunk_data.get("job_id")
            
            # [2025-05-26T19:20:00-04:00] Handle both content and chunk_data fields for compatibility
            chunk_content = chunk_data.get("content", chunk_data.get("chunk_data", ""))
            
            # Validate chunk metadata
            if not all([chunk_id is not None, total_chunks, message_id, message_hash, original_type]):
                logger.error(f"[2025-05-26T19:08:00-04:00] [base_worker.py] Invalid chunk metadata: {chunk_data}")
                return
            
            # Initialize message entry if it doesn't exist
            if message_id not in self.chunked_messages:
                self.chunked_messages[message_id] = {
                    "chunks": {},
                    "total_chunks": total_chunks,
                    "message_hash": message_hash,
                    "original_type": original_type,
                    "job_id": job_id,
                    "received_at": time.time()
                }
                logger.debug(f"[2025-05-26T19:08:00-04:00] [base_worker.py] Started receiving chunked message {message_id} with {total_chunks} chunks")
            
            # Store the chunk
            self.chunked_messages[message_id]["chunks"][chunk_id] = chunk_content
            received_chunks = len(self.chunked_messages[message_id]["chunks"])
            
            # Check if all chunks have been received
            if received_chunks == total_chunks:
                logger.debug(f"[2025-05-26T19:08:00-04:00] [base_worker.py] All {total_chunks} chunks received for message {message_id}, reassembling")
                
                # Sort chunks by chunk_id and concatenate
                sorted_chunks = [self.chunked_messages[message_id]["chunks"][i] for i in range(total_chunks)]
                complete_message = "".join(sorted_chunks)
                
                # Process the reassembled message
                logger.debug(f"[2025-05-26T19:08:00-04:00] [base_worker.py] Processing reassembled message of type {original_type}")
                
                # Parse the complete message
                try:
                    # Parse the message using MessageModels
                    message_data = json.loads(complete_message)
                    message_obj = self.message_models.parse_message(message_data)
                    
                    if not message_obj:
                        logger.error(f"[2025-05-26T19:08:00-04:00] [base_worker.py] Invalid reassembled message format: {complete_message[:300]}...")
                    else:
                        # Process the message based on its type
                        await self.handle_message(websocket, complete_message)
                except json.JSONDecodeError as e:
                    logger.error(f"[2025-05-26T19:08:00-04:00] [base_worker.py] Error parsing reassembled message: {str(e)}")
                    logger.error(f"[2025-05-26T19:08:00-04:00] [base_worker.py] Message sample: {complete_message[:500]}...")
                
                # Clean up the chunks to free memory
                del self.chunked_messages[message_id]
            else:
                # Still waiting for more chunks
                logger.debug(f"[2025-05-26T19:08:00-04:00] [base_worker.py] Waiting for more chunks: {received_chunks}/{total_chunks} for message {message_id}")
        
        except Exception as e:
            logger.error(f"[2025-05-26T19:08:00-04:00] [base_worker.py] Error handling chunked message: {str(e)}")
            logger.error(f"[2025-05-26T19:08:00-04:00] [base_worker.py] Stack trace: {traceback.format_exc()}")
    
    async def handle_message(self, websocket, message):
        """Handle incoming message from Redis Hub
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
            message: The raw message string
        """
        try:
            # [2025-05-23T09:15:08-04:00] Added message size logging to debug incoming WebSocket size issues
            message_size = len(message)
            
            # Log message size if it's large
            if message_size > 100000:  # Log messages larger than ~100KB
                logger.warning(f"[base_worker.py handle_message()] Large incoming message detected: {message_size} bytes")
                
                # If it's really large, log more details to help debugging
                if message_size > 500000:  # ~500KB
                    logger.error(f"[base_worker.py handle_message()] Very large incoming message: {message_size} bytes")
                    # Log a sample of the message to help identify what's causing the size issue
                    logger.error(f"[base_worker.py handle_message()] Message sample: {message[:500]}...")
            
            # Parse the message using MessageModels
            message_data = json.loads(message)
            
            # [2025-05-26T19:10:00-04:00] Check if this is a chunked message
            if message_data.get("type") == "chunked_message":
                # This is a chunk of a larger message, handle it specially
                logger.debug(f"[2025-05-26T19:10:00-04:00] [base_worker.py] Received chunked message part")
                await self._handle_chunked_message(websocket, message_data)
                return
                
            # Regular (non-chunked) message processing
            message_obj = self.message_models.parse_message(message_data)
            
            if not message_obj:
                logger.error(f"[base_worker.py handle_message()]: Invalid message format: {message[:300]}...")
                return
            
            message_type = message_obj.type            
            # Handle message based on type
            match(message_type):
                case MessageType.CONNECTION_ESTABLISHED:
                    logger.debug(f"[base_worker.py handle_message()]: Connection established: {getattr(message_obj, 'message', '')}")
                case MessageType.JOB_AVAILABLE:
                    # Ensure we have a JobAvailableMessage or compatible dict
                    if hasattr(message_obj, 'job_id') and hasattr(message_obj, 'job_type'):
                        await self.handle_job_notification(websocket, cast(Any, message_obj))
                    else:
                        logger.warning(f"[base_worker.py handle_message()]: Received JOB_AVAILABLE message with invalid format")
                case MessageType.JOB_ASSIGNED:
                    await self.handle_job_assigned(websocket, cast(Any, message_obj))
                
                case MessageType.WORKER_HEARTBEAT:
                    # Acknowledge heartbeat from server with detailed logging
                    logger.debug(f"[base_worker.py handle_message()]: HEARTBEAT RESPONSE RECEIVED from server for worker {self.worker_id}")
                
                case MessageType.WORKER_HEARTBEAT_ACK:
                    # Handle heartbeat acknowledgment from server
                    logger.debug(f"[base_worker.py handle_message()]: HEARTBEAT ACK RECEIVED from server for worker {self.worker_id}")
                case MessageType.JOB_COMPLETED_ACK:
                    # Handle job completion acknowledgment from the server
                    if hasattr(message_obj, 'job_id'):
                        job_id = message_obj.job_id
                        logger.debug(f"[base_worker.py handle_message()]: Job completion acknowledged by server: {job_id}")
                    else:
                        logger.warning(f"[base_worker.py handle_message()]: Received JOB_COMPLETED_ACK message with invalid format")
                
                case MessageType.JOB_FAILED_ACK:
                    # 2025-04-17-16:01 - Added handler for JOB_FAILED_ACK message
                    # Handle job failure acknowledgment from the server
                    if hasattr(message_obj, 'job_id'):
                        job_id = message_obj.job_id
                        error = getattr(message_obj, 'error', 'Unknown error')
                        logger.error(f"[base_worker.py handle_message()]: Job failure acknowledged by server: {job_id} - Error: {error}")
                        
                        # Ensure worker state is reset to idle
                        if self.status != WorkerStatus.IDLE:
                            logger.error(f"[base_worker.py handle_message()]: Resetting worker state to idle after job failure acknowledgment")
                            self.status = WorkerStatus.IDLE
                            self.current_job_id = None
                    else:
                        logger.error(f"[base_worker.py handle_message()]: Received JOB_FAILED_ACK message with invalid format")
                
                case MessageType.WORKER_REGISTERED:
                    # Handle worker registration confirmation
                    worker_id = getattr(message_obj, 'worker_id', self.worker_id)
                    logger.debug(f"[base_worker.py handle_message()]: Worker registration confirmed: {worker_id}")
                    # No further action needed, this is just an acknowledgment
                case MessageType.ERROR:
                    # Handle error messages from the server
                    error_text = getattr(message_obj, 'error', 'Unknown error')
                    logger.error(f"[base_worker.py handle_message()]: Received error from server: {error_text}")
                    
                    # If we're in a non-idle state and the error is related to job claiming,
                    # reset the worker state to idle
                    if self.status != WorkerStatus.IDLE and "claim job" in error_text.lower():
                        logger.error(f"[base_worker.py handle_message()]: Resetting worker state to idle after claim error")
                        self.status = WorkerStatus.IDLE
                        self.current_job_id = None
                
                # case MessageType.ACK:
                #     # Handle generic acknowledgment messages from the server
                #     # 2025-04-17-16:02 - Removed fail_job specific handling as it's now handled by JOB_FAILED_ACK
                #     original_id = getattr(message_obj, 'original_id', None)
                #     original_type = getattr(message_obj, 'original_type', None)
                #     logger.debug(f"[base_worker.py handle_message()]: Received ACK from server for {original_type} message with ID {original_id}")
                # case _:
                #     logger.debug(f"[base_worker.py handle_message()]: Received unhandled message type: {message_type}")
        except json.JSONDecodeError:
            logger.error(f"[base_worker.py handle_message()]: Invalid JSON: {message[:100]}...")
        except Exception as e:
            logger.error(f"[base_worker.py handle_message()]: Error handling message: {str(e)}")

    async def handle_job_notification(self, websocket, message_obj):
        """Handle job notification message from the Redis Hub
        
        Args:
            websocket: The websocket connection
            message_obj: The message object
        """
        try:
            # [2025-05-26T01:15:00-04:00] Enhanced debug logging for job notification handling
            logger.debug(f"[2025-05-26T01:15:00-04:00] Received job notification: {message_obj}")
            
            # First check if worker is idle before proceeding
            if self.status != WorkerStatus.IDLE:
                logger.debug(f"[2025-05-26T01:15:00-04:00] Ignoring job notification - worker is busy. Status: {self.status}")
                return
                
            # Extract job details safely with fallbacks
            job_id = None
            job_type = 'unknown'
            priority = 0
            last_failed_worker = None
                       
            # Try different ways to access message data
            if isinstance(message_obj, dict):
                # It's a dictionary
                job_id = message_obj.get('job_id')
                job_type = message_obj.get('job_type', 'unknown')
                priority = message_obj.get('priority', 0)
                last_failed_worker = message_obj.get('last_failed_worker')
            elif hasattr(message_obj, 'job_id'):
                # It has direct attributes (like a Pydantic model)
                job_id = message_obj.job_id
                job_type = getattr(message_obj, 'job_type', 'unknown')
                priority = getattr(message_obj, 'priority', 0)
                last_failed_worker = getattr(message_obj, 'last_failed_worker', None)
            
            # Log job notification with timestamp for tracking
            logger.debug(f"[base_worker.py handle_job_notification()]: Processing job notification. Job ID: {job_id}, Job Type: {job_type}, Priority: {priority}")
            
            # Check if job ID is present
            if not job_id:
                # Try one more approach - direct attribute access if the object has a string representation with job_id
                if hasattr(message_obj, '__str__'):
                    msg_str = str(message_obj)
                    if 'job_id' in msg_str:
                        import re
                        job_id_match = re.search(r"job_id='([^']+)'|job_id=\"([^\"]+)\"", msg_str)
                        if job_id_match:
                            job_id = job_id_match.group(1) or job_id_match.group(2)
                            
                            # Also try to extract job_type
                            job_type_match = re.search(r"job_type='([^']+)'|job_type=\"([^\"]+)\"", msg_str)
                            if job_type_match:
                                job_type = job_type_match.group(1) or job_type_match.group(2)
                
                # If still no job_id, return
                if not job_id:
                    logger.error(f"[base_worker.py handle_job_notification()]: Failed to extract job_id from message")
                    return
            
            # [2025-05-25T20:45:00-04:00] Enhanced debug logging for connector matching
            # [2025-05-25T21:05:00-04:00] Added None check for self.connectors to fix type errors
            if self.connectors is None:
                logger.error(f"[2025-05-25T21:05:00-04:00] No connectors available to handle job type '{job_type}'")
                return
                
            available_connectors = list(self.connectors.keys())
            logger.debug(f"[2025-05-25T20:45:00-04:00] Checking if job type '{job_type}' is in available connectors: {available_connectors}")
            
            # Check each connector's job_type and connector_id for debugging
            for connector_key, connector in self.connectors.items():
                try:
                    connector_id = connector.connector_id if hasattr(connector, 'connector_id') else 'unknown'
                    connector_job_type = connector.get_job_type() if hasattr(connector, 'get_job_type') else 'unknown'
                    logger.debug(f"[2025-05-25T20:45:00-04:00] Connector key='{connector_key}', connector_id='{connector_id}', job_type='{connector_job_type}'")
                except Exception as e:
                    logger.error(f"[2025-05-25T20:45:00-04:00] Error getting connector info: {e}")
            
            # First try exact match on job_type
            if job_type in self.connectors:
                logger.debug(f"[2025-05-25T20:45:00-04:00] Found exact match for job_type '{job_type}' in connectors")
            else:
                # If not found, try to find a connector with matching connector_id
                logger.error(f"[2025-05-25T20:45:00-04:00] Job type '{job_type}' not found in connector keys. Checking connector_id values...")
                
                matching_connector_key = None
                for connector_key, connector in self.connectors.items():
                    try:
                        if hasattr(connector, 'connector_id') and connector.connector_id == job_type:
                            matching_connector_key = connector_key
                            logger.debug(f"[2025-05-25T20:45:00-04:00] Found connector with connector_id '{job_type}' under key '{connector_key}'")
                            break
                    except Exception as e:
                        logger.error(f"[2025-05-25T20:45:00-04:00] Error checking connector_id: {e}")
                
                # If we found a matching connector by connector_id, use that key
                if matching_connector_key:
                    logger.debug(f"[2025-05-25T20:45:00-04:00] Using connector key '{matching_connector_key}' for job type '{job_type}' based on connector_id match")
                    # No need to modify self.connectors here, just continue with the job notification
                else:
                    # No matching connector found by job_type or connector_id
                    logger.error(f"[2025-05-25T20:45:00-04:00] Unsupported job type: '{job_type}'. Available connectors: {available_connectors}")
                    return
            
            # At this point, we've either found an exact match or a connector_id match
            # Continue with job notification processing
            
            # [2025-05-25T20:50:00-04:00] Extract job details from message object if not already done
            if hasattr(message_obj, 'job_id'):
                # It has direct attributes
                job_id = message_obj.job_id
                job_type = getattr(message_obj, 'job_type', 'unknown')
                priority = getattr(message_obj, 'priority', 0)
                last_failed_worker = getattr(message_obj, 'last_failed_worker', None)
            else:
                # Try to parse as JSON string
                try:
                    import json
                    if isinstance(message_obj, str):
                        parsed = json.loads(message_obj)
                        job_id = parsed.get('job_id')
                        job_type = parsed.get('job_type', 'unknown')
                        priority = parsed.get('priority', 0)
                        last_failed_worker = parsed.get('last_failed_worker')
                except Exception as e:
                    logger.error(f"[base_worker.py handle_job_notification()]: Failed to parse message as JSON: {str(e)}")
            
            # Check if we got a job_id
            if job_id is None:
                logger.error(f"[base_worker.py handle_job_notification()]: Job notification missing job_id")
                return
            
            # Check if this worker previously failed this job
            if last_failed_worker and last_failed_worker == self.worker_id:
                return
                        
            # Check if connectors are initialized
            if self.connectors is None:
                logger.error(f"[base_worker.py handle_job_notification()]: Connectors not initialized yet")
                return
                
            # [2025-05-25T22:37:00-04:00] Added detailed debug logging for job type matching
            # Check if we can handle this job type
            if self.connectors is not None:
                # Log available connectors and their types
                connector_types = list(self.connectors.keys())
                logger.debug(f"[base_worker.py handle_job_notification() DEBUG] Available connectors: {connector_types}")
                logger.debug(f"[base_worker.py handle_job_notification() DEBUG] Received job notification with job_type: '{job_type}'")
                
                # Check if job_type is in our connectors
                if job_type not in self.connectors:
                    logger.error(f"[base_worker.py handle_job_notification()]: Received job notification for unsupported job type: '{job_type}'")
                    logger.error(f"[base_worker.py handle_job_notification() DEBUG] Job type '{job_type}' not in available connectors: {connector_types}")
                    return
                else:
                    logger.debug(f"[base_worker.py handle_job_notification() DEBUG] Job type '{job_type}' is supported by this worker")
            
            # [2025-05-25T22:37:00-04:00] Added detailed debug logging for job claiming
            # Claim the job using ClaimJobMessage class
            claim_message = ClaimJobMessage(
                worker_id=self.worker_id,
                job_id=job_id
            )
            
            # Log the claim message for debugging
            claim_message_json = claim_message.model_dump_json()
            logger.debug(f"[base_worker.py handle_job_notification() DEBUG] Claiming job {job_id} of type '{job_type}' with message: {claim_message_json}")
                        
            await websocket.send(claim_message_json)
            logger.debug(f"[base_worker.py handle_job_notification() DEBUG] Sent claim message for job {job_id}")
            
            # Note: We don't update worker state here - we'll wait for JOB_ASSIGNED message
            # This matches the behavior in main.bk.py
        except Exception as e:
            logger.error(f"[base_worker.py handle_job_notification()]: Error handling job notification: {str(e)}")
    
    async def handle_job_assigned(self, websocket, message_obj):
        """Handle job assigned message from Redis Hub
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
            message_obj: The job assigned message object
        """
        # [2025-05-25T18:45:00-04:00] Completely rewritten method to fix syntax errors
        # and ensure proper A1111 job processing
        
        # Variables to track job info
        job_id = None
        job_type = None
        payload = None
        connector = None
        
        try:
            # Enhanced debug logging for job assignment
            logger.debug(f"[2025-05-25T18:45:00-04:00] Received job assignment message: {message_obj}")
            
            # Extract job details safely with fallbacks
            if isinstance(message_obj, dict):
                # It's a dictionary
                job_id = message_obj.get('job_id')
                job_type = message_obj.get('job_type')
                payload = message_obj.get('params', {})
            else:
                # Using explicit try/except to handle attribute access safely
                try:
                    job_id = message_obj.job_id if hasattr(message_obj, "job_id") else None
                except (AttributeError, TypeError):
                    job_id = None
                    
                try:
                    job_type = message_obj.job_type if hasattr(message_obj, "job_type") else None
                except (AttributeError, TypeError):
                    job_type = None
                    
                try:
                    payload = message_obj.params if hasattr(message_obj, "params") else {}
                except (AttributeError, TypeError):
                    payload = {}
            
            # Log job assignment with timestamp for tracking
            logger.debug(f"[2025-05-25T18:45:00-04:00] Processing job assignment. Job ID: {job_id}, Job Type: {job_type}")
            
            # Check if job ID is present
            if not job_id:
                logger.error(f"[2025-05-25T18:45:00-04:00] Missing job ID in job assigned message: {message_obj}")
                return
            
            # Check if job type is present
            if not job_type:
                logger.error(f"[2025-05-25T18:45:00-04:00] Missing job type in job assigned message: {message_obj}")
                return
            
            # [2025-05-25T21:20:00-04:00] Added None check for self.connectors to fix type errors
            if self.connectors is None:
                error_msg = f"No connectors available to handle job type '{job_type}'"
                logger.error(f"[2025-05-25T21:20:00-04:00] {error_msg}")
                await self.send_job_failed(websocket, job_id, error_msg)
                return
                
            # Enhanced debug logging for connector matching
            available_connectors = list(self.connectors.keys())
            logger.debug(f"[2025-05-25T18:45:00-04:00] Checking if job type '{job_type}' is in available connectors: {available_connectors}")
            
            # Check each connector's job_type and connector_id for debugging
            for connector_key, connector_instance in self.connectors.items():
                try:
                    connector_id = connector_instance.connector_id if hasattr(connector_instance, 'connector_id') else 'unknown'
                    connector_job_type = connector_instance.get_job_type() if hasattr(connector_instance, 'get_job_type') else 'unknown'
                    logger.debug(f"[2025-05-25T18:45:00-04:00] Connector key='{connector_key}', connector_id='{connector_id}', job_type='{connector_job_type}'")
                except Exception as e:
                    logger.error(f"[2025-05-25T18:45:00-04:00] Error getting connector info: {e}")
            
            # [2025-05-25T21:25:00-04:00] Added type assertion to fix type errors
            # We already checked for None above, so this is safe
            from typing import Dict, cast
            connectors_dict = cast(Dict[str, Any], self.connectors)
            
            # [2025-05-25T20:55:00-04:00] Enhanced job type matching logic
            # First try exact match on job_type
            connector_key = None
            if job_type in connectors_dict:
                logger.debug(f"[2025-05-25T20:55:00-04:00] Found exact match for job_type '{job_type}' in connectors")
                connector_key = job_type
            else:
                # If not found, try to find a connector with matching connector_id
                logger.error(f"[2025-05-25T20:55:00-04:00] Job type '{job_type}' not found in connector keys. Checking connector_id values...")
                
                for key, connector in connectors_dict.items():
                    try:
                        if hasattr(connector, 'connector_id') and connector.connector_id == job_type:
                            connector_key = key
                            logger.debug(f"[2025-05-25T20:55:00-04:00] Found connector with connector_id '{job_type}' under key '{key}'")
                            break
                    except Exception as e:
                        logger.error(f"[2025-05-25T20:55:00-04:00] Error checking connector_id: {e}")
            
            # If no matching connector found by job_type or connector_id
            if not connector_key:
                error_msg = f"Unsupported job type: {job_type}"
                logger.error(f"[2025-05-25T20:55:00-04:00] {error_msg}. Available connectors: {available_connectors}")
                await self.send_job_failed(websocket, job_id, error_msg)
                return
            
            # Log the selected connector
            logger.debug(f"[2025-05-25T20:55:00-04:00] Using connector '{connector_key}' for job type '{job_type}'")
            
            # Get the connector instance
            # [2025-05-25T21:30:00-04:00] Use the type-safe connectors_dict to avoid type errors
            connector = connectors_dict[connector_key]
            
            # Update worker state
            self.status = WorkerStatus.BUSY
            self.current_job_id = job_id
            
            # Update status to busy
            busy_status = WorkerStatusMessage(
                worker_id=self.worker_id,
                status="busy",
                capabilities={"job_id": job_id}
            )
            await websocket.send(busy_status.model_dump_json())
            logger.debug(f"[2025-05-25T18:45:00-04:00] Sent busy status update for job {job_id}")
            
            # [2025-05-25T21:00:00-04:00] We already have the connector instance from the enhanced job type matching logic above
            # No need to check connectors again or look up the connector by job_type
            
            # Check if the connector is healthy before processing the job
            logger.debug(f"[2025-05-25T21:00:00-04:00] Checking health of connector '{connector_key}' before processing job {job_id}")
            
            # Check if the connector has a health check method
            if hasattr(connector, 'check_health') and callable(connector.check_health):
                try:
                    is_healthy = await connector.check_health()
                    if not is_healthy:
                        error_msg = f"Connector '{connector_key}' failed health check"
                        logger.error(f"[2025-05-25T21:00:00-04:00] {error_msg}")
                        
                        # Send error progress update
                        await self.send_progress_update(
                            websocket, job_id, 0, "error", error_msg
                        )
                        
                        # Send job failure message
                        await self.send_job_failed(websocket, job_id, error_msg)
                        return
                    else:
                        logger.debug(f"[2025-05-25T21:00:00-04:00] Connector '{connector_key}' health check passed")
                except Exception as e:
                    logger.warning(f"[2025-05-25T21:00:00-04:00] Error during connector health check: {e}")
                    # Continue despite health check error - the job might still succeed
            else:
                logger.error(f"[2025-05-25T21:00:00-04:00] Connector '{connector_key}' does not support health checks")
                
            # Log the connector that will be used
            logger.debug(f"[2025-05-25T18:45:00-04:00] Using connector {type(connector).__name__} for job type '{job_type}'")
            
            # Log the job parameters
            try:
                logger.debug(f"[2025-05-25T18:45:00-04:00] Job parameters: {payload}")
            except Exception as e:
                logger.error(f"[2025-05-25T18:45:00-04:00] Error logging job parameters: {e}")
                
            # Send started progress update
            await self.send_progress_update(
                websocket, job_id, 0, "started", 
                f"Starting job with {type(connector).__name__}"
            )
            
            # Process the job with the connector
            try:
                # Process the job with the connector
                logger.debug(f"[2025-05-25T18:45:00-04:00] Processing job {job_id} with connector {type(connector).__name__}")
                
                # Call the process_job method on the connector
                result = await connector.process_job(
                    websocket, job_id, payload, 
                    lambda job_id, progress, status, message: self.send_progress_update(websocket, job_id, progress, status, message)
                )
                
                # Check if the result indicates a failure
                if isinstance(result, dict) and result.get("status") == "failed":
                    error_msg = result.get("error", "Unknown error")
                    logger.error(f"[2025-05-25T18:45:00-04:00] Job {job_id} failed: {error_msg}")
                    
                    # Send error progress update
                    await self.send_progress_update(websocket, job_id, 0, "error", f"Job failed: {error_msg}")
                    
                    # Send job failure message
                    job_id_str = str(job_id) if job_id is not None else "unknown_job"
                    fail_message = FailJobMessage(
                        job_id=job_id_str,
                        worker_id=self.worker_id,
                        error=error_msg
                    )
                    await websocket.send(fail_message.model_dump_json())
                    logger.error(f"[2025-05-25T18:45:00-04:00] Sent failure message for job {job_id}")
                else:
                    # Job completed successfully
                    logger.debug(f"[2025-05-25T18:45:00-04:00] Job {job_id} completed successfully")
                    
                    # Send completion progress update
                    await self.send_progress_update(websocket, job_id, 100, "completed", "Job completed successfully")
                    
                    # Send job completion message
                    job_id_str = str(job_id) if job_id is not None else "unknown_job"
                    complete_message = CompleteJobMessage(
                        worker_id=self.worker_id,
                        job_id=job_id_str,
                        result=result
                    )
                    await websocket.send(complete_message.model_dump_json())
                    logger.debug(f"[2025-05-25T18:45:00-04:00] Sent completion message for job {job_id}")
            except Exception as e:
                # Log the error
                error_msg = f"Error processing job {job_id}: {str(e)}"
                logger.error(f"[2025-05-25T18:45:00-04:00] {error_msg}")
                
                # Send error progress update
                await self.send_progress_update(
                    websocket, job_id, 0, "error", error_msg
                )
                
                # Send job failed message
                job_id_str = str(job_id) if job_id is not None else "unknown_job"
                fail_message = FailJobMessage(
                    job_id=job_id_str,
                    worker_id=self.worker_id,
                    error=str(e)
                )
                await websocket.send(fail_message.model_dump_json())
                logger.error(f"[2025-05-25T18:45:00-04:00] Sent failure message for job {job_id}")
            finally:
                # Reset worker state
                self.status = WorkerStatus.IDLE
                self.current_job_id = None
                
                # Update status back to idle
                idle_status = WorkerStatusMessage(
                    worker_id=self.worker_id,
                    status="idle"
                )
                
                # Send idle status update
                await websocket.send(idle_status.model_dump_json())
                logger.debug(f"[2025-05-25T18:45:00-04:00] Worker status reset to idle after job {job_id}")
        except Exception as e:
            # Log the error
            logger.error(f"[2025-05-25T18:45:00-04:00] Error handling job assignment: {str(e)}")
            
            # Try to send job failed message if possible
            try:
                if job_id:
                    await self.send_job_failed(websocket, job_id, f"Internal error: {str(e)}")
            except Exception as nested_e:
                logger.error(f"[2025-05-25T18:45:00-04:00] Error sending job failure: {str(nested_e)}")
            
            # Reset worker state
            self.status = WorkerStatus.IDLE
            self.current_job_id = None
    
    async def register_worker(self, websocket):
        """Register worker with Redis Hub
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
        """
        try:
            # Debug logging before registration
            logger.debug(f"[base_worker.py register_worker()]: Worker capabilities before registration: {self.capabilities}")
            
            # Ensure capabilities is a proper dictionary
            capabilities_dict = dict(self.capabilities) if self.capabilities else {}
            
            # Make sure supported_job_types is included
            if "supported_job_types" not in capabilities_dict and self.connectors:
                capabilities_dict["supported_job_types"] = list(self.connectors.keys())
                
            logger.debug(f"[base_worker.py register_worker()]: Prepared capabilities for registration: {capabilities_dict}")
            
            # Create registration message using RegisterWorkerMessage class
            registration_message = RegisterWorkerMessage(
                worker_id=self.worker_id,
                capabilities=capabilities_dict,
                subscribe_to_jobs=True,
                status=self.status.name.lower()
            )
            
            # Log the actual message being sent
            message_json = registration_message.model_dump_json()
            logger.debug(f"[base_worker.py register_worker()]: Registration message JSON: {message_json}")
            
            # Verify the message contains capabilities
            import json
            parsed_message = json.loads(message_json)
            logger.debug(f"[base_worker.py register_worker()]: Parsed message capabilities: {parsed_message.get('capabilities')}")
            
            # Send registration message
            await websocket.send(message_json)
            logger.debug(f"Registered worker with ID: {self.worker_id}")
            logger.debug(f"Capabilities: {self.capabilities}")
        except Exception as e:
            logger.error(f"Error registering worker: {str(e)}")
    
    async def shutdown_connectors(self):
        """Shutdown all connectors"""
        if self.connectors is None:
            return
        for job_type, connector in self.connectors.items():
            try:
                await connector.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down connector for {job_type}: {str(e)}")
    
    async def run(self):
        """Run the worker"""
        try:
            # Connect to Redis Hub
            logger.debug(f"Connecting to Redis Hub at {self.redis_ws_url}")
            async with websockets.connect(self.redis_ws_url) as websocket:
                logger.debug("Connected to Redis Hub")
                
                # Register worker
                await self.register_worker(websocket)
                
                # Start heartbeat task
                heartbeat_task = asyncio.create_task(self.send_heartbeat(websocket))
                
                # [2025-05-26T19:12:00-04:00] Start periodic chunk cleanup task
                chunk_cleanup_task = asyncio.create_task(self._periodic_chunk_cleanup())
                logger.debug(f"[2025-05-26T19:12:00-04:00] [base_worker.py] Started periodic chunk cleanup task: {chunk_cleanup_task}")
                
                logger.debug(f"[base_worker.py run()]: after heartbeat task setup {self.worker_id} {heartbeat_task}")
                
                # Note: WebSocket monitoring has been removed in favor of job-specific heartbeats
                # Each connector now handles its own connection lifecycle and sends heartbeats during active jobs
                connector_ws_monitor_tasks: list[asyncio.Task] = []  # Keep empty list for compatibility

                # Process messages
                async for message in websocket:
                    await self.handle_message(websocket, message)
                
                # Cancel heartbeat task
                heartbeat_task.cancel()
                
                # [2025-05-26T19:13:00-04:00] Cancel chunk cleanup task
                chunk_cleanup_task.cancel()
                logger.debug(f"[2025-05-26T19:13:00-04:00] [base_worker.py] Cancelled chunk cleanup task")
                
                # No connector WebSocket monitor tasks to cancel (feature removed)
        except Exception as e:
            logger.error(f"Error in worker: {str(e)}")
        finally:
            # No connector WebSocket monitor tasks to cancel (feature removed)
            
            # Shutdown connectors
            await self.shutdown_connectors()
    
    async def start(self):
        """Start the worker"""
        logger.debug(f"Starting worker with ID: {self.worker_id}")
        
        # Debug: Check current event loop
        try:
            current_loop = asyncio.get_running_loop()
            logger.debug(f"Current event loop: {current_loop}")
        except RuntimeError:
            logger.debug("No running event loop found")
        
        await self.run()
