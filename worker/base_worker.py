#!/usr/bin/env python3
# Base worker for the EmProps Redis Worker
import os
import sys
import asyncio
import json
import uuid
import websockets
from typing import Dict, List, Any, Optional, Union, cast
from enum import Enum, auto
from dotenv import load_dotenv



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

# Use a step-by-step approach to avoid multiple import errors
logger.info("[base_worker.py] Attempting to import required modules")

# Try different import approaches in sequence
import_success = False

# Approach 1: Try importing from worker package (best practice)
try:
    logger.info("[base_worker.py] Attempting to import from worker package")
    from worker import ConnectorInterface as WorkerConnectorInterface
    from worker import load_connectors as worker_load_connectors
    from worker import get_worker_capabilities as worker_get_capabilities
    
    ConnectorInterface = WorkerConnectorInterface
    load_connectors = worker_load_connectors
    get_worker_capabilities = worker_get_capabilities
    
    logger.info("[base_worker.py] Successfully imported from worker package")
    import_success = True
except ImportError as e:
    logger.info(f"[base_worker.py] Failed to import from worker package: {str(e)}")

# Approach 2: Try direct imports (for Docker container)
if not import_success:
    try:
        logger.info("[base_worker.py] Attempting direct imports")
        from connector_interface import ConnectorInterface as DirectConnectorInterface
        from connector_loader import load_connectors as direct_load_connectors
        from connector_loader import get_worker_capabilities as direct_get_capabilities
        
        ConnectorInterface = DirectConnectorInterface
        load_connectors = direct_load_connectors
        get_worker_capabilities = direct_get_capabilities
        
        logger.info("[base_worker.py] Successfully imported directly")
        import_success = True
    except ImportError as e2:
        logger.info(f"[base_worker.py] Failed direct imports: {str(e2)}")

# Approach 3: Try emp-redis-worker specific imports (for new Docker structure)
if not import_success:
    try:
        logger.info("[base_worker.py] Attempting emp-redis-worker specific imports")
        from emp_redis_worker.worker import ConnectorInterface as EmpConnectorInterface
        from emp_redis_worker.worker import load_connectors as emp_load_connectors
        from emp_redis_worker.worker import get_worker_capabilities as emp_get_capabilities
        
        ConnectorInterface = EmpConnectorInterface
        load_connectors = emp_load_connectors
        get_worker_capabilities = emp_get_capabilities
        
        logger.info("[base_worker.py] Successfully imported from emp_redis_worker.worker")
        import_success = True
    except ImportError as e3:
        logger.info(f"[base_worker.py] Failed emp-redis-worker imports: {str(e3)}")

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
        # Load connectors
        self.connectors = await load_connectors()   # Load connectors           
        
        # Initialize connectors
        logger.info(f"[base_worker.py async_init()] Initializing connectors...{self.connectors}")
        
        # Worker capabilities
        self.capabilities = await get_worker_capabilities(self.connectors)
        
        logger.info(f"[base_worker.py async_init()] Worker capabilities: {self.capabilities}")
        
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
        logger.debug("[base_worker.py send_heartbeat()]: 0")
        """Send heartbeat messages to keep the connection alive
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
        """
        try:
            print(f"[PRINT] Starting heartbeat for worker {self.worker_id}")  # Direct print
            logger.debug(f"[base_worker.py send_heartbeat()]: Starting heartbeat for worker {self.worker_id}")
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
                    logger.debug(f"[base_worker.py send_heartbeat()]: HEARTBEAT SENT")
                    # Wait for next heartbeat
                    await asyncio.sleep(self.heartbeat_interval)
                except Exception as e:
                    logger.error(f"[base_worker.py send_heartbeat()]: Error sending heartbeat: {str(e)}")
                    await asyncio.sleep(5)  # Wait before retrying
        except Exception as e:
            logger.error(f"[base_worker.py send_heartbeat()]: Fatal error for worker {self.worker_id}: {str(e)}")
    
    async def send_progress_update(self, websocket, job_id: str, progress: int, status: str = "processing", message: Optional[str] = None):
        """Send a progress update for a job
        
        Args:
            websocket: The WebSocket connection to send the update through
            job_id: The ID of the job being processed
            progress: Progress percentage (0-100 or -1 for heartbeats)
            status: Current job status (default: "processing")
            message: Optional status message
        """
        logger.debug(f"[base_worker.py send_progress_update()]: TESTING")
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
                    # Get connection details from the connector
                    connector = self.connectors[active_job_type]
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
            
            # Send the progress update
            await websocket.send(progress_message.model_dump_json())
            logger.debug(f"[base_worker.py send_progress_update()]: Sent progress update for job {job_id}: {progress}% - {message if message else status}")
            
        except Exception as e:
            logger.error(f"[base_worker.py send_progress_update()]: Error sending progress update for job {job_id}: {str(e)}")
    
    async def handle_message(self, websocket, message):
        """Handle incoming message from Redis Hub
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
            message: The raw message string
        """
        try:
            # Parse the message using MessageModels
            message_data = json.loads(message)
            message_obj = self.message_models.parse_message(message_data)
            
            if not message_obj:
                logger.info(f"[base_worker.py handle_message()]: Invalid message format: {message[:300]}...")
                return
            
            message_type = message_obj.type
            logger.info(f"[base_worker.py handle_message()]: Received message of type: {message_type}")
            
            # Handle message based on type
            match(message_type):
                case MessageType.CONNECTION_ESTABLISHED:
                    logger.info(f"[base_worker.py handle_message()]: Connection established: {getattr(message_obj, 'message', '')}")
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
                    logger.info(f"[base_worker.py handle_message()]: HEARTBEAT RESPONSE RECEIVED from server for worker {self.worker_id}")
                
                case MessageType.WORKER_HEARTBEAT_ACK:
                    # Handle heartbeat acknowledgment from server
                    logger.info(f"[base_worker.py handle_message()]: HEARTBEAT ACK RECEIVED from server for worker {self.worker_id}")
                case MessageType.JOB_COMPLETED_ACK:
                    # Handle job completion acknowledgment from the server
                    if hasattr(message_obj, 'job_id'):
                        job_id = message_obj.job_id
                        logger.info(f"[base_worker.py handle_message()]: Job completion acknowledged by server: {job_id}")
                    else:
                        logger.warning(f"[base_worker.py handle_message()]: Received JOB_COMPLETED_ACK message with invalid format")
                
                case MessageType.JOB_FAILED_ACK:
                    # 2025-04-17-16:01 - Added handler for JOB_FAILED_ACK message
                    # Handle job failure acknowledgment from the server
                    if hasattr(message_obj, 'job_id'):
                        job_id = message_obj.job_id
                        error = getattr(message_obj, 'error', 'Unknown error')
                        logger.info(f"[base_worker.py handle_message()]: Job failure acknowledged by server: {job_id} - Error: {error}")
                        
                        # Ensure worker state is reset to idle
                        if self.status != WorkerStatus.IDLE:
                            logger.info(f"[base_worker.py handle_message()]: Resetting worker state to idle after job failure acknowledgment")
                            self.status = WorkerStatus.IDLE
                            self.current_job_id = None
                    else:
                        logger.warning(f"[base_worker.py handle_message()]: Received JOB_FAILED_ACK message with invalid format")
                
                case MessageType.WORKER_REGISTERED:
                    # Handle worker registration confirmation
                    worker_id = getattr(message_obj, 'worker_id', self.worker_id)
                    logger.info(f"[base_worker.py handle_message()]: Worker registration confirmed: {worker_id}")
                    # No further action needed, this is just an acknowledgment
                case MessageType.ERROR:
                    # Handle error messages from the server
                    error_text = getattr(message_obj, 'error', 'Unknown error')
                    logger.warning(f"[base_worker.py handle_message()]: Received error from server: {error_text}")
                    
                    # If we're in a non-idle state and the error is related to job claiming,
                    # reset the worker state to idle
                    if self.status != WorkerStatus.IDLE and "claim job" in error_text.lower():
                        logger.info(f"[base_worker.py handle_message()]: Resetting worker state to idle after claim error")
                        self.status = WorkerStatus.IDLE
                        self.current_job_id = None
                
                case MessageType.ACK:
                    # Handle generic acknowledgment messages from the server
                    # 2025-04-17-16:02 - Removed fail_job specific handling as it's now handled by JOB_FAILED_ACK
                    original_id = getattr(message_obj, 'original_id', None)
                    original_type = getattr(message_obj, 'original_type', None)
                    logger.info(f"[base_worker.py handle_message()]: Received ACK from server for {original_type} message with ID {original_id}")
                case _:
                    logger.debug(f"[base_worker.py handle_message()]: Received unhandled message type: {message_type}")
        except json.JSONDecodeError:
            logger.error(f"[base_worker.py handle_message()]: Invalid JSON: {message[:100]}...")
        except Exception as e:
            logger.error(f"[base_worker.py handle_message()]: Error handling message: {str(e)}")

    async def handle_job_notification(self, websocket, message_obj):
        """Handle job notification message from Redis Hub
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
            message_obj: The job notification message object
        """
        try:
            # 2025-04-25-18:45 - Add comprehensive logging to understand message structure
            logger.info(f"""[base_worker.py handle_job_notification()]
╔══════════════════════════════════════════════════════════════════════════════╗
║ JOB NOTIFICATION RECEIVED - DETAILED MESSAGE STRUCTURE                      ║
║ Message Type: {type(message_obj)}                                            ║
║ Worker ID: {self.worker_id}                                                   ║
║ Raw Message: {str(message_obj)[:500]}                                         ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
            
            # First check if worker is idle before proceeding
            if self.status != WorkerStatus.IDLE:
                logger.info(f"[base_worker.py handle_job_notification()]: Ignoring job notification - worker is busy")
                return
                
            # Extract job details safely with fallbacks
            job_id = None
            job_type = 'unknown'
            priority = 0
            last_failed_worker = None
            
            # Log all available attributes and methods
            if hasattr(message_obj, '__dict__'):
                logger.info(f"[base_worker.py handle_job_notification()]: Message attributes: {message_obj.__dict__}")
            
            # Try different ways to access message data
            if isinstance(message_obj, dict):
                # It's a dictionary
                logger.info(f"[base_worker.py handle_job_notification()]: Message is a dictionary with keys: {message_obj.keys()}")
                job_id = message_obj.get('job_id')
                job_type = message_obj.get('job_type', 'unknown')
                priority = message_obj.get('priority', 0)
                last_failed_worker = message_obj.get('last_failed_worker')
            elif hasattr(message_obj, 'job_id'):
                # It has direct attributes
                logger.info(f"[base_worker.py handle_job_notification()]: Message has direct attributes")
                job_id = message_obj.job_id
                job_type = getattr(message_obj, 'job_type', 'unknown')
                priority = getattr(message_obj, 'priority', 0)
                last_failed_worker = getattr(message_obj, 'last_failed_worker', None)
            else:
                # Try to parse as JSON string
                logger.info(f"[base_worker.py handle_job_notification()]: Trying to parse message as JSON string")
                try:
                    import json
                    if isinstance(message_obj, str):
                        parsed = json.loads(message_obj)
                        job_id = parsed.get('job_id')
                        job_type = parsed.get('job_type', 'unknown')
                        priority = parsed.get('priority', 0)
                        last_failed_worker = parsed.get('last_failed_worker')
                        logger.info(f"[base_worker.py handle_job_notification()]: Successfully parsed JSON with keys: {parsed.keys()}")
                except Exception as e:
                    logger.error(f"[base_worker.py handle_job_notification()]: Failed to parse message as JSON: {str(e)}")
            
            # Check if we got a job_id
            if job_id is None:
                logger.error(f"[base_worker.py handle_job_notification()]: Job notification missing job_id")
                return
            
            # Log the extracted values
            logger.info(f"""[base_worker.py handle_job_notification()]
╔══════════════════════════════════════════════════════════════════════════════╗
║ EXTRACTED JOB NOTIFICATION VALUES                                           ║
║ Job ID: {job_id}                                                             ║
║ Job Type: {job_type}                                                          ║
║ Priority: {priority}                                                          ║
║ Last Failed Worker: {last_failed_worker}                                      ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
            
            # Check if this worker previously failed this job
            if last_failed_worker and last_failed_worker == self.worker_id:
                # Log with eye-catching format to make it obvious in the logs
                logger.info(f"""[base_worker.py handle_job_notification()]
╔══════════════════════════════════════════════════════════════════════════════╗
║ IGNORING JOB NOTIFICATION - WORKER PREVIOUSLY FAILED THIS JOB                ║
║ Job ID: {job_id}                                                             ║
║ Worker ID: {self.worker_id}                                                   ║
║ Last Failed Worker: {last_failed_worker}                                      ║
║ Job Type: {job_type}                                                          ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
                return
            
            logger.info(f"[base_worker.py handle_job_notification()]: Received job notification - job_id: {job_id}, type: {job_type}, priority: {priority}")
            
            # Check if connectors are initialized
            if self.connectors is None:
                logger.error(f"[base_worker.py handle_job_notification()]: Connectors not initialized yet")
                return
                
            # Check if we can handle this job type
            if self.connectors is not None and job_type not in self.connectors:
                logger.warning(f"[base_worker.py handle_job_notification()]: Received job notification for unsupported job type: {job_type}")
                return
            
            # Claim the job using ClaimJobMessage class
            claim_message = ClaimJobMessage(
                worker_id=self.worker_id,
                job_id=job_id
            )
            
            # Add debug logging to show worker state before claiming
            logger.debug(f"[base_worker.py handle_job_notification()]: Worker state before claiming job {job_id}: {self.status.name}")
            
            # Send claim request
            logger.info(f"[base_worker.py handle_job_notification()]: Sending claim request for job {job_id}")
            await websocket.send(claim_message.model_dump_json())
            
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

        logger.info(f"[base_worker.py handle_job_assigned] Received job assigned message: {message_obj}")
        
        try:
            # Extract job details safely with fallbacks
            if isinstance(message_obj, dict):
                job_id = message_obj.get("job_id")
                job_type = message_obj.get("job_type", "unknown")
                payload = message_obj.get("params", {})
            else:
                # Using explicit try/except to handle attribute access safely
                try:
                    job_id = message_obj.job_id if hasattr(message_obj, "job_id") else None
                except (AttributeError, TypeError):
                    job_id = None
                    
                try:
                    job_type = message_obj.job_type if hasattr(message_obj, "job_type") else "unknown"
                except (AttributeError, TypeError):
                    job_type = "unknown"
                    
                try:
                    payload = message_obj.params if hasattr(message_obj, "params") else {}
                except (AttributeError, TypeError):
                    payload = {}
            
            # Ensure job_id is not None
            if job_id is None:
                logger.error(f"[base_worker.py handle_job_assigned()]: Cannot process job: missing job_id")
                return
            
            logger.info(f"[base_worker.py handle_job_assigned()]: Processing job {job_id} of type {job_type}")
            
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
            
            # Check if connectors are initialized
            if self.connectors is None:
                logger.error(f"[base_worker.py handle_job_assigned()] Connectors not initialized yet")
                
                # Send error progress update
                await self.send_progress_update(
                    websocket, job_id, 0, "error", 
                    "Worker connectors not initialized"
                )
                
                # Send job failure message using FailJobMessage
                # Updated: 2025-04-17T15:15:00-04:00 - Using FailJobMessage with detailed logging
                job_id_str = str(job_id) if job_id is not None else "unknown_job"
                fail_message = FailJobMessage(
                    job_id=job_id_str,
                    worker_id=self.worker_id,
                    error="Worker connectors not initialized"
                )
                
                # Add detailed logging to verify the message is being sent
                fail_message_json = fail_message.model_dump_json()
                logger.info(f"[base_worker.py handle_job_assigned()]: SENDING FAIL_JOB MESSAGE: {fail_message_json}")
                
                # Send the message
                await websocket.send(fail_message_json)
                logger.info(f"[base_worker.py handle_job_assigned()]: Sent FailJobMessage for job {job_id_str} to be requeued")
                
                # Reset worker state
                self.status = WorkerStatus.IDLE
                self.current_job_id = None
                return
            
            # Get the appropriate connector for this job type
            connector = self.connectors.get(job_type)
            
            if connector is None:
                logger.error(f"[base_worker.py handle_job_assigned()] No connector available for job type: {job_type}")
                
                # Send error progress update
                await self.send_progress_update(
                    websocket, job_id, 0, "error", 
                    f"No connector available for job type: {job_type}"
                )
                
                # Send job failure message using FailJobMessage
                # Updated: 2025-04-17T15:15:00-04:00 - Using FailJobMessage with detailed logging
                job_id_str = str(job_id) if job_id is not None else "unknown_job"
                fail_message = FailJobMessage(
                    job_id=job_id_str,
                    worker_id=self.worker_id,
                    error=f"No connector available for job type: {job_type}"
                )
                
                # Add detailed logging to verify the message is being sent
                fail_message_json = fail_message.model_dump_json()
                logger.info(f"[base_worker.py handle_job_assigned()]: SENDING FAIL_JOB MESSAGE: {fail_message_json}")
                
                # Send the message
                await websocket.send(fail_message_json)
                logger.info(f"[base_worker.py handle_job_assigned()]: Sent FailJobMessage for job {job_id_str} to be requeued")
                
                # Reset worker state
                self.status = WorkerStatus.IDLE
                self.current_job_id = None
                
                # Update status back to idle
                idle_status = WorkerStatusMessage(
                    worker_id=self.worker_id,
                    status="idle"
                )
                await websocket.send(idle_status.model_dump_json())
                logger.info(f"[base_worker.py handle_job_assigned()]: Worker status reset to idle")
                return
            
            try:
                # Process the job using the connector
                # Send initial progress update
                await self.send_progress_update(websocket, job_id, 0, "started", f"Starting {job_type} job")
                
                # Updated: 2025-04-17T15:05:00-04:00 - Improved error handling for job completion
                result = await connector.process_job(
                    websocket, job_id, payload, 
                    lambda job_id, progress, status, message: self.send_progress_update(websocket, job_id, progress, status, message)
                )
                
                # Check if the result indicates a failure
                is_failed = False
                if isinstance(result, dict) and result.get("status") == "failed":
                    is_failed = True
                    error_msg = result.get("error", "Unknown error")
                    logger.error(f"[base_worker.py handle_job_assigned()]: Job {job_id} failed: {error_msg}")
                    
                    # Send error progress update if not already sent
                    await self.send_progress_update(websocket, job_id, 0, "error", f"Job failed: {error_msg}")
                    
                    # Updated: 2025-04-17T15:23:00-04:00 - Using FailJobMessage for failed jobs
                    # Send job failure message using FailJobMessage
                    job_id_str = str(job_id) if job_id is not None else "unknown_job"
                    fail_message = FailJobMessage(
                        job_id=job_id_str,
                        worker_id=self.worker_id,
                        error=error_msg
                    )
                    
                    # Add detailed logging to verify the message is being sent
                    fail_message_json = fail_message.model_dump_json()
                    logger.info(f"[base_worker.py handle_job_assigned()]: SENDING FAIL_JOB MESSAGE FOR NORMAL FAILURE: {fail_message_json}")
                    
                    # Send the message
                    await websocket.send(fail_message_json)
                    logger.info(f"[base_worker.py handle_job_assigned()]: Sent FailJobMessage for job {job_id_str} to be requeued")
                else:
                    # Only send 100% completion update for successful jobs
                    await self.send_progress_update(websocket, job_id, 100, "completed", "Job completed successfully")
                    logger.info(f"[base_worker.py handle_job_assigned()]: Job {job_id} completed successfully")
                    
                    # Send job completion message using CompleteJobMessage class only for successful jobs
                    job_id_str = str(job_id) if job_id is not None else "unknown_job"
                    completion_message = CompleteJobMessage(
                        worker_id=self.worker_id,
                        job_id=job_id_str,
                        result=result
                    )
                    await websocket.send(completion_message.model_dump_json())
                
            except Exception as e:
                logger.error(f"[base_worker.py handle_job_assigned()]: Error processing job {job_id}: {str(e)}")
                
                # Send job failure message using FailJobMessage
                # Updated: 2025-04-17T15:15:00-04:00 - Using FailJobMessage with detailed logging
                job_id_str = str(job_id) if job_id is not None else "unknown_job"
                fail_message = FailJobMessage(
                    job_id=job_id_str,
                    worker_id=self.worker_id,
                    error=str(e)
                )
                
                # Add detailed logging to verify the message is being sent
                fail_message_json = fail_message.model_dump_json()
                logger.info(f"[base_worker.py handle_job_assigned()]: SENDING FAIL_JOB MESSAGE: {fail_message_json}")
                
                # Send the message
                await websocket.send(fail_message_json)
                logger.info(f"[base_worker.py handle_job_assigned()]: Sent FailJobMessage for job {job_id_str} to be requeued")
            
            finally:
                # Reset worker state
                self.status = WorkerStatus.IDLE
                self.current_job_id = None
                
                # Update status back to idle
                idle_status = WorkerStatusMessage(
                    worker_id=self.worker_id,
                    status="idle"
                )
                await websocket.send(idle_status.model_dump_json())
                logger.info(f"[base_worker.py handle_job_assigned()]: Worker status reset to idle")
                
        except Exception as e:
            logger.error(f"[base_worker.py handle_job_assigned()]: Error in handle_job_assigned: {str(e)}")
            
            # Reset worker state if we have an error at the top level
            self.status = WorkerStatus.IDLE
            self.current_job_id = None
    
    async def register_worker(self, websocket):
        """Register worker with Redis Hub
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
        """
        try:
            # Debug logging before registration
            logger.info(f"[base_worker.py register_worker()]: Worker capabilities before registration: {self.capabilities}")
            
            # Ensure capabilities is a proper dictionary
            capabilities_dict = dict(self.capabilities) if self.capabilities else {}
            
            # Make sure supported_job_types is included
            if "supported_job_types" not in capabilities_dict and self.connectors:
                capabilities_dict["supported_job_types"] = list(self.connectors.keys())
                
            logger.info(f"[base_worker.py register_worker()]: Prepared capabilities for registration: {capabilities_dict}")
            
            # Create registration message using RegisterWorkerMessage class
            registration_message = RegisterWorkerMessage(
                worker_id=self.worker_id,
                capabilities=capabilities_dict,
                subscribe_to_jobs=True,
                status=self.status.name.lower()
            )
            
            # Log the actual message being sent
            message_json = registration_message.model_dump_json()
            logger.info(f"[base_worker.py register_worker()]: Registration message JSON: {message_json}")
            
            # Verify the message contains capabilities
            import json
            parsed_message = json.loads(message_json)
            logger.info(f"[base_worker.py register_worker()]: Parsed message capabilities: {parsed_message.get('capabilities')}")
            
            # Send registration message
            await websocket.send(message_json)
            logger.info(f"Registered worker with ID: {self.worker_id}")
            logger.info(f"Capabilities: {self.capabilities}")
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
            logger.info(f"Connecting to Redis Hub at {self.redis_ws_url}")
            async with websockets.connect(self.redis_ws_url) as websocket:
                logger.info("Connected to Redis Hub")
                
                # Register worker
                await self.register_worker(websocket)
                
                # Start heartbeat task
                heartbeat_task = asyncio.create_task(self.send_heartbeat(websocket))
                
                logger.info(f"[base_worker.py run()]: after heartbeat task setup {self.worker_id} {heartbeat_task}")
                
                # Note: WebSocket monitoring has been removed in favor of job-specific heartbeats
                # Each connector now handles its own connection lifecycle and sends heartbeats during active jobs
                connector_ws_monitor_tasks: list[asyncio.Task] = []  # Keep empty list for compatibility

                # Process messages
                async for message in websocket:
                    await self.handle_message(websocket, message)
                
                # Cancel heartbeat task
                heartbeat_task.cancel()
                
                # No connector WebSocket monitor tasks to cancel (feature removed)
        except Exception as e:
            logger.error(f"Error in worker: {str(e)}")
        finally:
            # No connector WebSocket monitor tasks to cancel (feature removed)
            
            # Shutdown connectors
            await self.shutdown_connectors()
    
    async def start(self):
        """Start the worker"""
        logger.info(f"Starting worker with ID: {self.worker_id}")
        
            # Debug: Check current event loop
        try:
            current_loop = asyncio.get_running_loop()
            logger.info(f"Current event loop: {current_loop}")
        except RuntimeError:
            logger.info("No running event loop found")
        
        await self.run()
