#!/usr/bin/env python3
# Core WebSocket connection manager for the queue system
import json
import asyncio
import time
import os
from typing import Dict, Set, List, Any, Optional, Callable
from fastapi import WebSocket, FastAPI, Query
from fastapi.websockets import WebSocketDisconnect
from websockets.exceptions import ConnectionClosedError
from .core_types.base_messages import MessageType
from .message_models import (
    BaseMessage, 
    ErrorMessage,
    ConnectionEstablishedMessage,
    WorkerStatusMessage,
    UnknownMessage,
    AckMessage,
    SubscriptionConfirmedMessage,
    WorkerCapabilities
)
from .interfaces import ConnectionManagerInterface
from .utils.logger import logger

class ConnectionManager(ConnectionManagerInterface):
    """Manages WebSocket connections and message routing"""
    
    # Worker heartbeat timeout (in seconds)
    # Workers send heartbeats every 20 seconds, so 60 seconds is 3 missed heartbeats
    WORKER_HEARTBEAT_TIMEOUT = 60
    
    # Cleanup task interval (in seconds)
    CLEANUP_INTERVAL = 30
    
    def __init__(self):
        """Initialize connection manager"""
        # Maps client IDs to their WebSocket connections
        self.client_connections: Dict[str, WebSocket] = {}
        
        # Maps worker IDs to their WebSocket connections
        self.worker_connections: Dict[str, WebSocket] = {}
        
        # Maps monitor IDs to their WebSocket connections
        self.monitor_connections: Dict[str, WebSocket] = {}
        
        # Maps job IDs to client IDs that should receive updates
        self.job_subscriptions: Dict[str, str] = {}
        
        # Set of client IDs subscribed to system stats updates
        self.stats_subscriptions: Set[str] = set()
        
        # Set of worker IDs subscribed to job notifications
        self.job_notification_subscriptions: Set[str] = set()
        
        # Get authentication token from environment variable
        self.auth_token = os.environ.get("WEBSOCKET_AUTH_TOKEN", "")
        
        # Set of monitor IDs with their message type filters
        self.monitor_filters: Dict[str, Set[str]] = {}
        
        # Worker state management
        # Tracks worker status ("idle", "busy", etc.)
        self.worker_status: Dict[str, str] = {}
        
        # Tracks worker capabilities including supported job types
        self.worker_capabilities: Dict[str, Dict[str, Any]] = {}
        
        # Track worker heartbeats (worker_id -> timestamp)
        self.worker_last_heartbeat: Dict[str, float] = {}
        
        # Track worker jobs (worker_id -> job_id)
        self.worker_current_jobs: Dict[str, str] = {}
        
        # Track worker registration time and stats
        self.worker_info: Dict[str, Dict[str, Any]] = {}
        
        # 2025-04-25-23:05 - Added in-memory tracking for failed jobs per worker
        # This replaces the Redis-based last_failed_worker tracking with a more comprehensive approach
        # Maps worker_id to a set of job_ids that the worker has failed
        self.worker_failed_jobs: Dict[str, Set[str]] = {}
        
        # Reference to MessageHandler for delegating message processing
        self.message_handler = None
        self.redis_service = None
        
        # Start the worker cleanup task
        asyncio.create_task(self._cleanup_stale_workers())
        
    # Note: Stale worker detection and cleanup is now handled by the message handler's _mark_stale_workers_task
    # and the Redis service's mark_stale_workers method
    

    

    
    # Note: Stale worker detection and cleanup is now handled by the message handler's _mark_stale_workers_task
    # and the Redis service's mark_stale_workers method
    
    def record_failed_job(self, worker_id: str, job_id: str) -> None:
        """
        Record that a worker has failed a specific job
        
        This method updates the in-memory tracking of which jobs a worker has failed.
        This information is used to prevent reassigning failed jobs to the same worker.
        
        Args:
            worker_id: The ID of the worker that failed the job
            job_id: The ID of the job that failed
        """
        # 2025-04-25-23:15 - Added method to record failed jobs in memory
        logger.info(f"[connection_manager.py record_failed_job()] Recording that worker {worker_id} failed job {job_id}")
        
        # Initialize the set if it doesn't exist
        if worker_id not in self.worker_failed_jobs:
            self.worker_failed_jobs[worker_id] = set()
        
        # Add the job ID to the set of failed jobs for this worker
        self.worker_failed_jobs[worker_id].add(job_id)
        
        # Log the updated failed jobs for this worker
        logger.info(f"""[connection_manager.py record_failed_job()]
╔══════════════════════════════════════════════════════════════════════════════╗
║ WORKER FAILURE RECORDED                                                      ║
║ Worker ID: {worker_id}                                                       ║
║ Job ID: {job_id}                                                             ║
║ Total Failed Jobs: {len(self.worker_failed_jobs.get(worker_id, set()))}      ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
    
    def force_retry_job(self, job_id: str):
        """
        Force a job to be retried by clearing its failure history
        
        This method removes the job from all workers' failed jobs sets,
        allowing it to be assigned to any worker regardless of previous failures.
        
        Args:
            job_id: The ID of the job to force retry
            
        Returns:
            bool: True if the job was found in any worker's failed jobs set and cleared,
                  False otherwise
        
        [2025-05-19T18:01:00-04:00] Added to support force retry functionality
        """
        found = False
        cleared_workers = []
        
        # Check all workers' failed jobs sets for this job
        for worker_id, failed_jobs in self.worker_failed_jobs.items():
            if job_id in failed_jobs:
                # Remove this job from the worker's failed jobs set
                failed_jobs.remove(job_id)
                cleared_workers.append(worker_id)
                found = True
        
        if found:
            logger.info(f"""[connection_manager.py force_retry_job()]
╔══════════════════════════════════════════════════════════════════════════════╗
║ FORCE RETRY JOB                                                              ║
║ Job ID: {job_id}                                                             ║
║ Cleared from workers: {', '.join(cleared_workers)}                           ║
║ Action: Job failure history cleared, allowing reassignment to any worker     ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
        else:
            logger.info(f"""[connection_manager.py force_retry_job()]
╔══════════════════════════════════════════════════════════════════════════════╗
║ FORCE RETRY JOB - NO ACTION NEEDED                                           ║
║ Job ID: {job_id}                                                             ║
║ Reason: Job not found in any worker's failed jobs list                       ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
            
        return found
    
    async def disconnect_worker(self, worker_id: str) -> None:
        """
        Disconnect a worker and clean up its resources.
        
        Args:
            worker_id: ID of the worker to disconnect
        """
        try:
            # [2025-05-23T08:35:19-04:00] Enhanced worker cleanup to prevent stale worker records
            logger.info(f"[connection_manager.py disconnect_worker()] Disconnecting worker {worker_id} and cleaning up all resources")
            
            # Clean up local state
            if worker_id in self.worker_connections:
                # Close the WebSocket connection if it's still open
                try:
                    logger.debug(f"connection_manager.py disconnect_worker: Closing WebSocket connection for worker {worker_id}")
                    await self._close_websocket(self.worker_connections[worker_id], f"Worker {worker_id} disconnected")
                except Exception as e:
                    logger.warning(f"Error closing WebSocket for worker {worker_id}: {str(e)}")
                
                # Remove from local tracking
                del self.worker_connections[worker_id]
                logger.debug(f"Removed worker {worker_id} from worker_connections")
            
            # Remove worker from all tracking dictionaries
            # 1. Status tracking
            if worker_id in self.worker_status:
                del self.worker_status[worker_id]
                logger.debug(f"Removed worker {worker_id} from worker_status")
            
            # 2. Capabilities tracking
            if worker_id in self.worker_capabilities:
                del self.worker_capabilities[worker_id]
                logger.debug(f"Removed worker {worker_id} from worker_capabilities")
            
            # 3. Heartbeat tracking
            if worker_id in self.worker_last_heartbeat:
                del self.worker_last_heartbeat[worker_id]
                logger.debug(f"Removed worker {worker_id} from worker_last_heartbeat")
            
            # 4. Current jobs tracking
            if worker_id in self.worker_current_jobs:
                del self.worker_current_jobs[worker_id]
                logger.debug(f"Removed worker {worker_id} from worker_current_jobs")
            
            # 5. Worker info tracking
            if worker_id in self.worker_info:
                del self.worker_info[worker_id]
                logger.debug(f"Removed worker {worker_id} from worker_info")
            
            # 6. Failed jobs tracking
            if worker_id in self.worker_failed_jobs:
                del self.worker_failed_jobs[worker_id]
                logger.debug(f"Removed worker {worker_id} from worker_failed_jobs")
            
            # 7. Job notification subscriptions
            if worker_id in self.job_notification_subscriptions:
                self.job_notification_subscriptions.remove(worker_id)
                logger.debug(f"Removed worker {worker_id} from job_notification_subscriptions")
            
            logger.info(f"[connection_manager.py disconnect_worker()] Successfully disconnected worker {worker_id} and cleaned up all resources")
        except Exception as e:
            logger.error(f"Error disconnecting worker {worker_id}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    
    def init_routes(self, app: FastAPI) -> None:
        """
        Initialize routes for the FastAPI application.
        
        Args:
            app: FastAPI application instance. 
        """
        # Print to verify this method is being called
        #logger.debug_highlight("\n\n***** REGISTERING ROUTES IN CONNECTION_MANAGER.PY ====\n\n")
        
        # Register WebSocket routes

        # Client WebSocket route
        @app.websocket("/ws/client/{client_id}")
        async def client_websocket_route(websocket: WebSocket, client_id: str, token: str = Query(None)):
            #logger.debug_highlight(f"\n\n***** CLIENT WEBSOCKET ROUTE CALLED FOR {client_id} ====\n\n")
            # Check authentication token
            if not self._verify_auth_token(token):
                await websocket.accept()
                await websocket.send_text(json.dumps({"type": "error", "error": "Authentication failed: Invalid token"}))
                await websocket.close()
                return
            await self.client_websocket(websocket, client_id)
        
        # Worker WebSocket route
        @app.websocket("/ws/worker/{worker_id}")
        async def worker_websocket_route(websocket: WebSocket, worker_id: str, token: str = Query(None)):
            #logger.debug_highlight(f"\n\n***** WORKER WEBSOCKET ROUTE CALLED FOR {worker_id} ====\n\n")
            # Check authentication token
            if not self._verify_auth_token(token):
                await websocket.accept()
                await websocket.send_text(json.dumps({"type": "error", "error": "Authentication failed: Invalid token"}))
                await websocket.close()
                return
            await self.worker_websocket(websocket, worker_id)
        
        # Monitor WebSocket route
        @app.websocket("/ws/monitor/{monitor_id}")
        async def monitor_websocket_route(websocket: WebSocket, monitor_id: str, token: str = Query(None)):
            #logger.debug_highlight(f"\n\n***** MONITOR WEBSOCKET ROUTE CALLED FOR {monitor_id} ====\n\n")
            # Check authentication token
            if not self._verify_auth_token(token):
                await websocket.accept()
                await websocket.send_text(json.dumps({"type": "error", "error": "Authentication failed: Invalid token"}))
                await websocket.close()
                return
            await self.monitor_websocket(websocket, monitor_id)
        
        # Add a test route that doesn't require a parameter
            
            # Create chunk message
            chunk_message = {
                "type": "chunked_message",
                "message_id": message_id,
                "chunk_index": i,
                "chunk_count": chunk_count,
                "chunk_data": chunk.decode('utf-8'),
                "original_message_type": message.get("type", "unknown")
            }
            
            # Add progress information
            progress = (i + 1) / chunk_count * 100
            logger.debug(f"[connection_manager.py send_chunked_message()] Sending chunk {i+1}/{chunk_count} ({progress:.1f}%) to worker {worker_id}")
            
            # Send the chunk
            success = await self._send_raw_message_to_worker(websocket, chunk_message)
            if not success:
                logger.error(f"[connection_manager.py send_chunked_message()] Failed to send chunk {i+1}/{chunk_count} to worker {worker_id}")
                return False
                
        logger.info(f"[connection_manager.py send_chunked_message()] Successfully sent all {chunk_count} chunks to worker {worker_id}")
        return True
        
    # [2025-05-23T09:34:00-04:00] Added helper method for sending raw messages without chunking
    async def _send_raw_message_to_worker(self, websocket, message) -> bool:
        """Send a raw message to a worker without chunking
        
        This is used internally by send_chunked_message to avoid recursive chunking.
        
        Args:
            websocket: The WebSocket connection
            message: The message to send
            
        Returns:
            bool: True if sent successfully, False otherwise
        """
        try:
            # Serialize the message appropriately
            message_text = None
            message_type = type(message).__name__
            
            if hasattr(message, "model_dump_json"):
                # Handle newer Pydantic v2 models
                message_text = message.model_dump_json()
            elif hasattr(message, "json"):
                # Handle older Pydantic models
                message_text = message.json()
            elif isinstance(message, dict):
                message_text = json.dumps(message)
            else:
                message_text = str(message)
                
            # Send the message
            await websocket.send_text(message_text)
            logger.debug(f"[connection_manager.py _send_raw_message_to_worker()] Sent raw message to worker: {message_text}")
            return True
            
        except RuntimeError as e:
            if "WebSocket is not connected" in str(e) or "Connection is closed" in str(e):
                logger.warning(f"[connection_manager.py _send_raw_message_to_worker()] Failed to send raw message - connection closed")
            else:
                logger.error(f"[connection_manager.py _send_raw_message_to_worker()] Runtime error sending raw message: {str(e)}")
            return False
                
        except Exception as e:
            logger.error(f"[connection_manager.py _send_raw_message_to_worker()] Error sending raw message: {str(e)}")
            return False
    
    async def send_to_worker(self, worker_id: str, message: BaseMessage) -> bool:
        """Send a message to a specific worker"""
        # Check worker connection status
        if worker_id not in self.worker_connections:
            logger.debug(f"[WORKER-MSG] Cannot send to worker {worker_id} - not connected")
            return False
        
        # Get WebSocket connection
        websocket = self.worker_connections[worker_id]
        
        # [2025-05-23T09:32:00-04:00] Added automatic message chunking for large payloads
        # Convert message to JSON to check size
        message_text = json.dumps(message)
        msg_size = len(message_text)
        
        # Import the standardized limit
        try:
            from hub.main import MAX_WS_MESSAGE_SIZE_BYTES, MAX_WS_MESSAGE_SIZE_MB
        except ImportError:
            # Fallback if import fails
            MAX_WS_MESSAGE_SIZE_MB = int(os.environ.get('MAX_WS_MESSAGE_SIZE_MB', 100))
            MAX_WS_MESSAGE_SIZE_BYTES = MAX_WS_MESSAGE_SIZE_MB * 1024 * 1024
        
        # Define the threshold for chunking (80% of max size to leave room for metadata)
        CHUNK_THRESHOLD = int(MAX_WS_MESSAGE_SIZE_BYTES * 0.8)
        
        # If message is larger than the threshold, use chunking
        if msg_size > CHUNK_THRESHOLD:
            logger.info(f"[connection_manager.py send_to_worker()] Message size {msg_size/1024/1024:.2f}MB exceeds chunking threshold ({CHUNK_THRESHOLD/1024/1024:.2f}MB). Using chunked transfer.")
            return await self.send_chunked_message(websocket, message, CHUNK_THRESHOLD)
        
        try:
            # Serialize the message appropriately
            message_text = None
            message_type = type(message).__name__
            
            if hasattr(message, "model_dump_json"):
                # Handle newer Pydantic v2 models
                message_text = message.model_dump_json()
            elif hasattr(message, "json"):
                # Handle older Pydantic models
                message_text = message.json()
            elif isinstance(message, dict):
                message_text = json.dumps(message)
            else:
                message_text = str(message)
                
            # Extract message details for logging
            msg_type = "unknown"
            msg_id = "unknown"
            job_type = None
            last_failed_worker = None
            
            if isinstance(message, dict):
                if "type" in message:
                    msg_type = message["type"]
                if "id" in message:
                    msg_id = message["id"]
                elif "job_id" in message:
                    msg_id = message["job_id"]
                if "job_type" in message:
                    job_type = message["job_type"]
                # 2025-04-25-18:55 - Check for last_failed_worker field
                if "last_failed_worker" in message:
                    last_failed_worker = message["last_failed_worker"]
            elif hasattr(message, "type"):
                msg_type = message.type
                if hasattr(message, "id"):
                    msg_id = message.id
                elif hasattr(message, "job_id"):
                    msg_id = message.job_id
                if hasattr(message, "job_type"):
                    job_type = message.job_type
                # 2025-04-25-18:55 - Check for last_failed_worker field
                if hasattr(message, "last_failed_worker"):
                    last_failed_worker = message.last_failed_worker
            
            # Log concise message details
            log_details = f"type={msg_type}, id={msg_id}"
            if job_type:
                log_details += f", job_type={job_type}"
                
            # [2025-05-23T09:15:46-04:00] Enhanced message size logging to debug WebSocket size issues
            msg_size = len(message_text)
            
            # Always log message size
            logger.info(f"[WORKER-MSG] Sending to worker {worker_id}: {log_details} ({msg_size} bytes)")
            
            # Log more details for large messages
            if msg_size > 100000:  # Log messages larger than ~100KB
                logger.warning(f"[connection_manager.py send_to_worker()] Large outgoing message detected: {msg_size} bytes to worker {worker_id}, type={msg_type}")
                
                # If it's really large, log more details to help debugging
                if msg_size > 500000:  # ~500KB
                    logger.error(f"[connection_manager.py send_to_worker()] Very large outgoing message: {msg_size} bytes to worker {worker_id}")
                    # Log a sample of the message to help identify what's causing the size issue
                    logger.error(f"[connection_manager.py send_to_worker()] Message sample: {message_text[:500]}...")
                    
                    # Try to identify what's making the message so large
                    if hasattr(message, "model_dump"):
                        message_dict = message.model_dump()
                        for key, value in message_dict.items():
                            value_str = str(value)
                            value_size = len(value_str)
                            if value_size > 10000:  # Log fields larger than 10KB
                                logger.error(f"[connection_manager.py send_to_worker()] Large field '{key}': {value_size} bytes")
                                logger.error(f"[connection_manager.py send_to_worker()] Field '{key}' sample: {value_str[:200]}...")
            
            # [2025-05-23T09:15:46-04:00] Added message size limit check to prevent WebSocket errors
            # [2025-05-23T09:28:30-04:00] Updated to use standardized message size limit from environment
            # Import the standardized limit from hub.main
            try:
                from hub.main import MAX_WS_MESSAGE_SIZE_BYTES, MAX_WS_MESSAGE_SIZE_MB
            except ImportError:
                # Fallback if import fails
                MAX_WS_MESSAGE_SIZE_MB = int(os.environ.get('MAX_WS_MESSAGE_SIZE_MB', 100))
                MAX_WS_MESSAGE_SIZE_BYTES = MAX_WS_MESSAGE_SIZE_MB * 1024 * 1024
                
            if msg_size > MAX_WS_MESSAGE_SIZE_BYTES:
                logger.error(f"[connection_manager.py send_to_worker()] Message too large to send: {msg_size} bytes ({msg_size/1024/1024:.2f}MB). Max allowed: {MAX_WS_MESSAGE_SIZE_BYTES} bytes ({MAX_WS_MESSAGE_SIZE_MB}MB). Skipping to prevent WebSocket disconnection.")
                
                # Log information about large fields to help diagnose the issue
                try:
                    message_dict = json.loads(message_text)
                    for key, value in message_dict.items():
                        value_str = str(value)
                        value_size = len(value_str)
                        if value_size > 1000000:  # Log fields larger than 1MB
                            logger.error(f"[connection_manager.py send_to_worker()] Large field '{key}': {value_size/1024/1024:.2f}MB")
                            # Log a sample of the field content
                            logger.error(f"[connection_manager.py send_to_worker()] Field '{key}' sample: {value_str[:200]}...")
                except Exception as e:
                    logger.error(f"[connection_manager.py send_to_worker()] Error analyzing message content: {str(e)}")
                    
                return False
                
            # Actually send the message
            await websocket.send_text(message_text)
            
            # Add more detailed logging
            if msg_type == "job_available" and job_type:
                logger.info(f"[WORKER-MSG] Sent job notification for job type {job_type} to worker {worker_id}")
                if hasattr(message, "job_request_payload") and message.job_request_payload:
                    logger.info(f"[WORKER-MSG] Job request payload: {message.job_request_payload}")
                
                # 2025-04-25-18:55 - Add boxed logging for last_failed_worker field
                box_width = 80
                logger.info("╔" + "═" * (box_width - 2) + "╗")
                logger.info("║ JOB NOTIFICATION SERIALIZATION CHECK " + " " * (box_width - 38) + "║")
                logger.info("║" + "─" * (box_width - 2) + "║")
                logger.info(f"║ Job ID: {msg_id}" + " " * (box_width - 11 - len(str(msg_id))) + "║")
                logger.info(f"║ Job Type: {job_type}" + " " * (box_width - 13 - len(str(job_type))) + "║")
                logger.info(f"║ Worker ID: {worker_id}" + " " * (box_width - 14 - len(str(worker_id))) + "║")
                logger.info(f"║ Message Type: {msg_type}" + " " * (box_width - 17 - len(str(msg_type))) + "║")
                
                if last_failed_worker:
                    logger.info(f"║ Last Failed Worker: {last_failed_worker}" + " " * (box_width - 24 - len(str(last_failed_worker))) + "║")
                    logger.info("║ WORKER REASSIGNMENT: This job will NOT be reassigned to the last failed worker ║")
                else:
                    logger.info("║ Last Failed Worker: None" + " " * (box_width - 24 - 4) + "║")
                    logger.info("║ WORKER REASSIGNMENT: No last_failed_worker specified for this job" + " " * 12 + "║")
                
                # Log the actual serialized message content for debugging
                logger.info("║" + "─" * (box_width - 2) + "║")
                logger.info("║ Serialized Message Preview (first 50 chars):" + " " * (box_width - 47) + "║")
                preview = message_text[:50] + "..." if len(message_text) > 50 else message_text
                logger.info(f"║ {preview}" + " " * (box_width - 3 - len(preview)) + "║")
                logger.info("╚" + "═" * (box_width - 2) + "╝")
            
            # logger.debug(f"[WORKER-MSG] Successfully sent message to worker {worker_id}")
            return True
            
        except RuntimeError as e:
            error_msg = str(e)
            if "WebSocket is not connected" in error_msg or "Connection is closed" in error_msg:
                # logger.warning(f"[WORKER-MSG] Failed to send to worker {worker_id} - connection closed")
                await self.disconnect_worker(worker_id)
            else:
                logger.error(f"[WORKER-MSG] Runtime error sending to worker {worker_id}: {error_msg}")
            return False
                
        except Exception as e:
            logger.error(f"[WORKER-MSG] Error sending to worker {worker_id}: {str(e)}")
            return False
    
    # ... (rest of the code remains the same)
            # Send the message to the monitor
            websocket = self.monitor_connections[monitor_id]
            
            # Serialize the message appropriately - similar to send_to_client
            message_text = None
            
            if hasattr(message, "json"):
                # Use the message's json method if available
                message_text = message.json()
            elif isinstance(message, dict):
                # If it's a dictionary, use json.dumps
                message_text = json.dumps(message)
            else:
                # Fallback to string representation
                print(f"WARNING: Message type {type(message)} has no json method")
                message_text = str(message)
            
            # Send the serialized message
            await websocket.send_text(message_text)
            logger.debug(f"[MONITOR-MSG] Sent message to monitor {monitor_id}")
            return True
            
        except Exception as e:
            logger.error(f"[MONITOR-MSG] Error sending message to monitor {monitor_id}: {str(e)}")
            return False
    
    async def subscribe_to_job_notifications(self, worker_id: str, enabled: bool = True) -> bool:
        """Subscribe a worker to job notifications.
        
        Args:
            worker_id: ID of the worker subscribing
            enabled: Whether to enable or disable the subscription
            
        Returns:
            bool: True if subscription was successful, False otherwise
        """
        try:
            # Check if the worker is connected
            if worker_id not in self.worker_connections:
                logger.warning(f"[JOB-NOTIFY] Worker {worker_id} is not connected")
                return False
            
            if enabled:
                # Add the worker to the job notification subscriptions
                self.job_notification_subscriptions.add(worker_id)
                logger.info(f"[JOB-NOTIFY] Worker {worker_id} subscribed to job notifications")
                return True
            else:
                # Remove the worker from job notification subscriptions
                if worker_id in self.job_notification_subscriptions:
                    self.job_notification_subscriptions.remove(worker_id)
                    logger.info(f"[JOB-NOTIFY] Worker {worker_id} unsubscribed from job notifications")
                    return True
                return False
            
        except Exception as e:
            logger.error(f"[JOB-NOTIFY] Error subscribing worker {worker_id} to job notifications: {str(e)}")
            return False

    async def _cleanup_stale_workers(self):
        """Periodically check for and cleanup stale workers"""
        while True:
            try:
                current_time = time.time()
                stale_workers = []
                
                # Check each worker's last heartbeat
                for worker_id, last_heartbeat in self.worker_last_heartbeat.items():
                    heartbeat_age = current_time - last_heartbeat
                    if heartbeat_age > self.WORKER_HEARTBEAT_TIMEOUT:
                        stale_workers.append(worker_id)
                        logger.warning(f"Worker {worker_id} is stale (last heartbeat: {heartbeat_age:.1f}s ago)")
                
                # Disconnect stale workers
                for worker_id in stale_workers:
                    logger.info(f"Disconnecting stale worker {worker_id}")
                    await self.disconnect_worker(worker_id)
                    
                    # If Redis service is available, reassign any jobs from this worker
                    if self.redis_service:
                        await self.redis_service.reassign_worker_jobs(worker_id)
                
            except Exception as e:
                logger.error(f"Error in worker cleanup task: {str(e)}")
                
            # Wait before next cleanup check
            await asyncio.sleep(self.CLEANUP_INTERVAL)
            
    def register_worker(self, worker_id: str, capabilities: Optional[Dict[str, Any]] = None) -> bool:
        """Register a worker and store its capabilities
        
        Args:
            worker_id: Unique identifier for the worker
            capabilities: Optional worker capabilities including supported job types
            
        Returns:
            bool: True if registration was successful
        """
        try:
            current_time = time.time()
            
            # Store worker capabilities
            if capabilities:
                self.worker_capabilities[worker_id] = capabilities
            
            # Initialize worker info
            self.worker_info[worker_id] = {
                "registered_at": current_time,
                "last_heartbeat": current_time,
                "status": "idle",
                "current_job_id": "",
                "jobs_processed": 0,
                "last_job_completed_at": 0,
                "updated_at": current_time
            }
            
            # Initialize other worker state
            self.worker_status[worker_id] = "idle"
            self.worker_last_heartbeat[worker_id] = current_time
            
            logger.info(f"Worker {worker_id} registered successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error registering worker {worker_id}: {str(e)}")
            return False
            
    def get_worker_info(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a worker
        
        Args:
            worker_id: ID of the worker to get information about
            
        Returns:
            Optional[Dict[str, Any]]: Worker information if worker exists, None otherwise
        """
        if worker_id not in self.worker_info:
            return None
            
        # Return a copy of the worker info to prevent external modification
        return dict(self.worker_info[worker_id])
        
    def update_worker_job_assignment(self, worker_id: str, status: str, job_id: Optional[str] = None) -> bool:
        """Update worker status and job assignment
        
        This method provides comprehensive worker state management by updating:
        1. The worker's status in both worker_status and worker_info
        2. The worker's job assignment in worker_current_jobs and worker_info
        3. Timestamp information for tracking and monitoring
        
        Args:
            worker_id: ID of the worker to update
            status: New status (e.g., "idle", "busy", "working")
            job_id: Optional ID of the job the worker is processing
            
        Returns:
            bool: True if update was successful
        """
        try:
            if worker_id not in self.worker_info:
                logger.warning(f"[connection_manager.py update_worker_job_assignment] Worker {worker_id} not found in worker_info")
                return False
                
            current_time = time.time()
            
            # Update status
            self.worker_status[worker_id] = status
            self.worker_info[worker_id]["status"] = status
            self.worker_info[worker_id]["updated_at"] = current_time
            
            # Update job assignment
            if job_id:
                self.worker_current_jobs[worker_id] = job_id
                self.worker_info[worker_id]["current_job_id"] = job_id
                logger.debug(f"[connection_manager.py update_worker_job_assignment] Worker {worker_id} assigned to job {job_id}")
            elif status == "idle":
                # Clear job assignment when worker becomes idle
                if worker_id in self.worker_current_jobs:
                    self.worker_current_jobs.pop(worker_id, None)
                    logger.debug(f"[connection_manager.py update_worker_job_assignment] Worker {worker_id} job assignment cleared")
                self.worker_info[worker_id]["current_job_id"] = ""
                
            return True
            
        except Exception as e:
            logger.error(f"[connection_manager.py update_worker_job_assignment] Error updating worker {worker_id} status: {str(e)}")
            return False
