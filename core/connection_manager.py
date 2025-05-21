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
            # Clean up local state
            if worker_id in self.worker_connections:
                # Close the WebSocket connection if it's still open
                try:
                    logger.debug(f"connection_manager.py disconnect_worker: TIMEOUT AFTER 2 MINUTES: WHY? Closing WebSocket connection for worker {worker_id}")
                    await self._close_websocket(self.worker_connections[worker_id], f"Worker {worker_id} disconnected")
                except Exception:
                    pass
                
                # Remove from local tracking
                del self.worker_connections[worker_id]
            
            # Remove worker from status tracking so it doesn't appear in the UI
            if worker_id in self.worker_status:
                del self.worker_status[worker_id]
            
            # Remove worker capabilities from memory
            if worker_id in self.worker_capabilities:
                #logger.info(f"Removing capabilities for disconnected worker {worker_id}")
                del self.worker_capabilities[worker_id]
            
            if worker_id in self.worker_last_heartbeat:
                del self.worker_last_heartbeat[worker_id]
            
            # Always remove from job notification subscriptions when disconnected
            if worker_id in self.job_notification_subscriptions:
                self.job_notification_subscriptions.remove(worker_id)
            
            #logger.info(f"Disconnected worker {worker_id}")
        except Exception as e:
            logger.error(f"Error disconnecting worker {worker_id}: {str(e)}")
    
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
        @app.websocket("/ws/test")
        async def test_websocket_route(websocket: WebSocket):
            #logger.debug_highlight("\n\n*****  TEST WEBSOCKET ROUTE CALLED ====\n\n")
            await websocket.accept()
            await websocket.send_text(json.dumps({"type": "test", "message": "Test connection successful"}))
            await websocket.close()
            
    def _verify_auth_token(self, token: Optional[str]) -> bool:
        """Verify the authentication token.
        
        Args:
            token: The token to verify
            
        Returns:
            bool: True if token is valid, False otherwise
        """
        # If no auth token is set in environment, authentication is disabled
        if not self.auth_token:
            return True
            
        # Otherwise, verify the token
        return token == self.auth_token
    
    async def client_websocket(self, websocket: WebSocket, client_id: str) -> None:
        """
        Handle client WebSocket connections.
        
        Args:
            websocket: WebSocket connection
            client_id: Client identifier
        """
        #logger.debug(f"[CLIENT-CONN] Accepting connection for client: {client_id}")

        try:
            logger.debug_highlight(f"About to accept connection for client: {client_id}")
        except Exception as log_error:
            print(f"\n\n==== ERROR WITH LOGGER: {str(log_error)} ====\n\n")
        
        # Flag to track if connection is closed
        connection_closed = False
            
        # Accept the connection
        try:
            await websocket.accept()
            
            # Store the connection
            # print(f"\n\n==== STORING CONNECTION: {client_id} ====\n\n")
            self.client_connections[client_id] = websocket
            # print(f"\n\n==== CONNECTION STORED: {client_id} ====\n\n")
            
            # Send an immediate welcome message
            # print(f"\n\n==== SENDING WELCOME: {client_id} ====\n\n")
            welcome_message = ConnectionEstablishedMessage(
                message=f"Welcome Client {client_id}! Connected to Redis Hub"
            )
            await websocket.send_text(welcome_message.model_dump_json())
            # print(f"\n\n==== WELCOME SENT: {client_id} ====\n\n")
            
            # logger.info(f"Client connected: {client_id}")
        except Exception as e:
            # print(f"\n\n==== ERROR ACCEPTING CLIENT CONNECTION {client_id}: {str(e)} ====\n\n")
            # logger.error(f"Error accepting client connection {client_id}: {str(e)}")
            connection_closed = True
            return
        
        # Handle client messages
        try:
            while True:
                # Receive message from client
                message_text = await websocket.receive_text()
                
                # Parse message
                try:
                    message_data = json.loads(message_text)
                    message_type = message_data.get("type")
                    
                    # Delegate all message handling to MessageHandler
                    if self.message_handler is not None:
                        await self.message_handler.handle_client_message(client_id, message_type, message_data, websocket)
                    else:
                        error_message = ErrorMessage(error="Message handler not initialized")
                        await self.send_to_client(client_id, error_message)
                    
                except json.JSONDecodeError:
                    # Handle invalid JSON
                    error_message = ErrorMessage(error="Invalid JSON format")
                    await self.send_to_client(client_id, error_message)
                    
                except Exception as e:
                    # Handle processing error
                    error_message = ErrorMessage(error=f"Server error processing message: {str(e)}")
                    await self.send_to_client(client_id, error_message)
                
        except WebSocketDisconnect:
            if not connection_closed:
                self.disconnect_client(client_id)
                # logger.info(f"Client disconnected: {client_id}")
                connection_closed = True
        
        except Exception as e:
            # Handle unexpected error
            if not connection_closed:
                self.disconnect_client(client_id)
                # logger.error(f"Unexpected error in client connection {client_id}: {str(e)}")
                connection_closed = True
    
    async def worker_websocket(self, websocket: WebSocket, worker_id: str) -> None:
        """
        Handle worker WebSocket connections.
        
        Args:
            websocket: WebSocket connection
            worker_id: Worker identifier
        """
        #logger.debug(f"[WORKER-CONN] Accepting connection for worker {worker_id}.")
        # Flag to track if connection is closed
        connection_closed = False
        
        # Accept the connection
        try:
            # Accept the connection
            await websocket.accept()
            
            # Store the connection
            self.worker_connections[worker_id] = websocket
            self.worker_status[worker_id] = "idle"  # Set initial status to idle
            
            # Send an immediate welcome message
            welcome_message = {"type": "connection_established", "message": f"Welcome Worker {worker_id}! Connected to Redis Hub"}
            # logger.debug(f"[WORKER-CONN] Sending welcome message to worker {worker_id}")
            await websocket.send_text(json.dumps(welcome_message))
            
            # logger.info(f"Worker connected: {worker_id}")
        except WebSocketDisconnect as e:
            # logger.error(f"WebSocket disconnected during worker connection setup for {worker_id}: {str(e)}")
            connection_closed = True
            return
        except ConnectionClosedError as e:
            # logger.error(f"Connection closed during worker connection setup for {worker_id}: {str(e)}")
            connection_closed = True
            return
        except Exception as e:
            # logger.error(f"Error accepting worker connection {worker_id}: {str(e)}")
            connection_closed = True
            return
        
        try:
            while True:
                # Receive message from worker
                message_text = await websocket.receive_text()
                
                # Parse message
                try:
                    message_data = json.loads(message_text)
                    # logger.debug(f"Received message from worker {worker_id}: {message_data}")
                    
                    # Process message based on type
                    if self.message_handler is not None:
                        # Extract message type from message data
                        message_type = message_data.get("type", "unknown")
                        # Call with correct parameter order matching the interface
                        #logger.debug(f"Sending to Handler: {message_type} message from worker {worker_id}: {message_data}.")
                        await self.message_handler.handle_worker_message(worker_id, message_type, message_data, websocket)
                    else:
                        error_message = ErrorMessage(error="Message handler not initialized")
                        await self.send_to_worker(worker_id, error_message)
                        
                except json.JSONDecodeError:
                    # Handle invalid JSON
                    error_message = ErrorMessage(error="Invalid JSON format")
                    await self.send_to_worker(worker_id, error_message)
                    
                except Exception as e:
                    # Handle processing error
                    error_message = ErrorMessage(error=f"Server error processing message: {str(e)}")
                    await self.send_to_worker(worker_id, error_message)
                
        except WebSocketDisconnect:
            if not connection_closed:
                # disconnect_worker now handles setting status to disconnected
                await self.disconnect_worker(worker_id)
                #logger.info(f"Worker disconnected: {worker_id}")
                connection_closed = True
        
        except Exception as e:
            # Handle unexpected error
            if not connection_closed:
                # disconnect_worker now handles setting status to disconnected
                await self.disconnect_worker(worker_id)
                logger.error(f"Unexpected error in worker connection {worker_id}: {str(e)}")
                connection_closed = True
    
    async def monitor_websocket(self, websocket: WebSocket, monitor_id: str) -> None:
        """
        Handle monitor WebSocket connections.
        
        Args:
            websocket: WebSocket connection
            monitor_id: Monitor identifier
        """
        #logger.debug(f"[MONITOR-CONN] Accepting connection for monitor: {monitor_id}")
        # Flag to track if connection is closed
        connection_closed = False
        
        # Accept the connection
        try:
            await websocket.accept()
            
            # Store the connection
            self.monitor_connections[monitor_id] = websocket
            
            # Send an immediate welcome message
            welcome_message = ConnectionEstablishedMessage(
                message=f"Welcome Monitor {monitor_id}! Connected to Redis Hub"
            )
            await websocket.send_text(welcome_message.model_dump_json())
            
            # Send immediate system status update
            await self.send_system_status_to_monitors(self.redis_service)
            
            # logger.info(f"Monitor connected: {monitor_id}")
        except Exception as e:
            # logger.error(f"Error accepting monitor connection {monitor_id}: {str(e)}")
            connection_closed = True
            return
        
        try:
            while True:
                # Receive message from monitor
                message_text = await websocket.receive_text()
                
                # Parse message
                try:
                    message_data = json.loads(message_text)
                    message_type = message_data.get("type")
                    
                    # Delegate all message handling to MessageHandler
                    if self.message_handler is not None:
                        await self.message_handler.handle_monitor_message(monitor_id, message_type, message_data, websocket)
                    else:
                        error_message = ErrorMessage(error="Message handler not initialized")
                        await self.send_to_monitor(monitor_id, error_message)
                        
                except json.JSONDecodeError:
                    # Handle invalid JSON
                    error_message = ErrorMessage(error="Invalid JSON format")
                    await self.send_to_monitor(monitor_id, error_message)
                    
                except Exception as e:
                    # Handle processing error
                    error_message = ErrorMessage(error=f"Server error processing message: {str(e)}")
                    await self.send_to_monitor(monitor_id, error_message)
                
        except WebSocketDisconnect:
            if not connection_closed:
                self.disconnect_monitor(monitor_id)
                # logger.info(f"Monitor disconnected: {monitor_id}")
                connection_closed = True
        
        except Exception as e:
            # Handle unexpected error
            if not connection_closed:
                self.disconnect_monitor(monitor_id)
                # logger.error(f"Unexpected error in monitor connection {monitor_id}: {str(e)}")
                connection_closed = True

    async def connect_client(self, websocket: WebSocket, client_id: str) -> None:
        """Connect a client WebSocket"""
        try:
            # Check if client is already connected to avoid duplicate connections
            if client_id in self.client_connections:
                try:
                    old_websocket = self.client_connections[client_id]
                    logger.debug(f"BClosing WebSocket connection for worker {client_id}")
                    await self._close_websocket(old_websocket, f"Replaced by new connection for {client_id}")
                except Exception as e:
                    pass
            

            
            # We won't call websocket.accept() here since it's now handled in the router
            # This allows us to separate connection management from protocol handling
            self.client_connections[client_id] = websocket
            
            # Send a confirmation message to client
            try:
                welcome_message = {
                    "type": "connection_established",
                    "status": "connected", 
                    "client_id": client_id,
                    "message": "Successfully connected to Redis Hub"
                }
                await websocket.send_text(json.dumps(welcome_message))
            except Exception as e:
                pass
                
        except Exception as e:
            # Attempt to close connection gracefully if possible
            try:
                await websocket.close(code=1011, reason=f"Connection error: {str(e)}")
            except Exception:
                pass
            raise
    
    async def connect_worker(self, websocket: WebSocket, worker_id: str) -> None:
        """Connect a worker WebSocket"""
        try:
            # Check if worker is already connected to avoid duplicate connections
            if worker_id in self.worker_connections:
                try:
                    old_websocket = self.worker_connections[worker_id]
                    logger.debug(f"C Closing WebSocket connection for worker {worker_id}")
                    await self._close_websocket(old_websocket, f"Replaced by new connection for {worker_id}")
                except Exception:
                    pass
            

            
            # We won't call websocket.accept() here since it's now handled in the router
            # This allows us to separate connection management from protocol handling
            self.worker_connections[worker_id] = websocket
            self.worker_status[worker_id] = "idle"  # Set initial status to idle
            #logger.info(f"Worker {worker_id} connected successfully")
            
            # Send a confirmation message to worker
            try:
                welcome_message = {
                    "type": "connection_established",
                    "status": "connected", 
                    "worker_id": worker_id,
                    "message": "Successfully connected to Redis Hub"
                }
                await websocket.send_text(json.dumps(welcome_message))
            except Exception:
                pass
                
        except Exception as e:
            # Attempt to close connection gracefully if possible
            try:
                await websocket.close(code=1011, reason=f"Connection error: {str(e)}")
            except Exception:
                pass
            raise
    
    def disconnect_client(self, client_id: str) -> None:
        """Disconnect a client"""
        if client_id in self.client_connections:
            # Store reference to WebSocket object before deletion
            websocket = self.client_connections[client_id]
            
            # Clean up connections dict first
            del self.client_connections[client_id]
            
            # Clean up subscriptions
            if client_id in self.stats_subscriptions:
                self.stats_subscriptions.remove(client_id)
                
            # Clean up job subscriptions
            jobs_to_remove = []
            for job_id, subscriber_id in self.job_subscriptions.items():
                if subscriber_id == client_id:
                    jobs_to_remove.append(job_id)
            
            for job_id in jobs_to_remove:
                del self.job_subscriptions[job_id]
            

            
            # Try to close the connection gracefully (async context but sync function)
            try:
                logger.debug(f"D Closing WebSocket connection for client {client_id}")
                asyncio.create_task(self._close_websocket(websocket, f"Client {client_id} disconnected"))
            except Exception:
                pass
                
    async def connect_monitor(self, websocket: WebSocket, monitor_id: str) -> None:
        """Connect a monitor WebSocket"""
        try:
            # Check if monitor is already connected to avoid duplicate connections
            if monitor_id in self.monitor_connections:
                try:
                    old_websocket = self.monitor_connections[monitor_id]
                    logger.debug(f"E Closing WebSocket connection for monitor {monitor_id}")
                    await self._close_websocket(old_websocket, f"Replaced by new connection for {monitor_id}")
                except Exception:
                    pass
            

            
            # We won't call websocket.accept() here since it's now handled in the router
            # This allows us to separate connection management from protocol handling
            self.monitor_connections[monitor_id] = websocket
            self.monitor_filters[monitor_id] = set()  # Initialize with empty filter set (receive all messages)
            
            # Send a confirmation message to monitor
            try:
                welcome_message = {
                    "type": "connection_established",
                    "status": "connected", 
                    "monitor_id": monitor_id,
                    "message": "Successfully connected to Redis Hub Monitor API"
                }
                await websocket.send_text(json.dumps(welcome_message))
            except Exception:
                pass
                
        except Exception as e:
            # Attempt to close connection gracefully if possible
            try:
                await websocket.close(code=1011, reason=f"Connection error: {str(e)}")
            except Exception:
                pass
            raise
    
    def disconnect_monitor(self, monitor_id: str) -> None:
        """Disconnect a monitor"""
        if monitor_id in self.monitor_connections:
            # Store reference to WebSocket object before deletion
            websocket = self.monitor_connections[monitor_id]
            
            # Clean up connections dict first
            del self.monitor_connections[monitor_id]
            
            # Clean up monitor filters
            if monitor_id in self.monitor_filters:
                del self.monitor_filters[monitor_id]
                

            
            # Try to close the connection gracefully (async context but sync function)
            try:
                logger.debug(f"F Closing WebSocket connection for monitor {monitor_id}")
                asyncio.create_task(self._close_websocket(websocket, f"Monitor {monitor_id} disconnected"))
            except Exception:
                pass
    
    def is_worker_connected(self, worker_id: str) -> bool:
        """Check if a worker is connected"""
        return worker_id in self.worker_connections
    
    async def subscribe_to_job(self, client_id: str, job_id: str) -> bool:
        """Subscribe a client to job updates"""
        # Check if client is connected before subscribing
        logger.debug(f"[SUBSCRIBE] Client {client_id} subscribing to job {job_id}")
        is_connected = client_id in self.client_connections
        if not is_connected:
            return False
        
        # Record previous subscription if exists
        prev_client = self.job_subscriptions.get(job_id)
        
        # Update subscription mapping
        self.job_subscriptions[job_id] = client_id
        return True
    
    def subscribe_to_stats(self, client_id: str) -> None:
        """Subscribe a client to system stats updates"""
        self.stats_subscriptions.add(client_id)
        
    def unsubscribe_from_stats(self, client_id: str) -> None:
        """Unsubscribe a client from system stats updates"""
        if client_id in self.stats_subscriptions:
            self.stats_subscriptions.remove(client_id)
    
    async def send_to_client(self, client_id: str, message: BaseMessage) -> bool:
        """Send a message to a specific client"""
        # Check client connection status
        if client_id not in self.client_connections:
            return False
        
        # Get WebSocket connection
        websocket = self.client_connections[client_id]
        
        try:
            # Serialize the message appropriately
            message_text = None
            message_type = type(message).__name__
            
            if hasattr(message, "json"):
                message_text = message.json()
            elif isinstance(message, dict):
                message_text = json.dumps(message)
            else:
                message_text = str(message)
            
            # Send the original message
            await websocket.send_text(message_text)
            logger.debug(f"[connection_manager.py send_to_client()] Sent message of type {type(message).__name__} to client {client_id}: {message_text}")
            
            # [2025-05-20T19:23:00-04:00] Check message type - we no longer need to send complete_job messages here
            # The message_handler.py now handles this directly in the correct order
            try:
                parsed_message = json.loads(message_text) if isinstance(message_text, str) else message_text
                
                # Log information about the message being sent
                if isinstance(parsed_message, dict):
                    message_type = parsed_message.get("type")
                    job_id = parsed_message.get("job_id")
                    status = parsed_message.get("status")
                    
                    if message_type == "complete_job":
                        # This is a complete_job message sent directly from message_handler.py
                        logger.info(f"[2025-05-20T19:23:00-04:00] Forwarding complete_job message for job {job_id}")
                    elif message_type == "update_job_progress" and status == "completed":
                        # This is a job completion update - we'll just forward it as is
                        # The complete_job message will be sent separately by message_handler.py
                        logger.info(f"[2025-05-20T19:23:00-04:00] Forwarding job completion update for job {job_id}")
                        
                # We no longer need to query Redis or send additional messages here
                # The message_handler.py now handles this in the correct sequence
                    
                # [2025-05-20T19:24:00-04:00] We no longer need to send a complete_job message here
                # This is now handled by message_handler.py in the correct sequence
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
                
            return True
            
        except RuntimeError as e:
            if "WebSocket is not connected" in str(e) or "Connection is closed" in str(e):
                self.disconnect_client(client_id)
            return False
                
        except Exception as e:
            logger.error(f"[connection_manager.py send_to_client()] Error sending message: {str(e)}")
            return False
    
    async def send_to_worker(self, worker_id: str, message: BaseMessage) -> bool:
        """Send a message to a specific worker"""
        # Check worker connection status
        if worker_id not in self.worker_connections:
            logger.debug(f"[WORKER-MSG] Cannot send to worker {worker_id} - not connected")
            return False
        
        # Get WebSocket connection
        websocket = self.worker_connections[worker_id]
        
        try:
            # Serialize the message appropriately
            message_text = None
            message_type = type(message).__name__
            
            if hasattr(message, "model_dump_json"):
                # Handle newer Pydantic v2 models
                message_text = message.model_dump_json()
                # logger.debug(f"[WORKER-MSG] Using model_dump_json() method for serialization")
            elif hasattr(message, "json"):
                # Handle older Pydantic models
                message_text = message.json()
                # logger.debug(f"[WORKER-MSG] Using .json() method for serialization")
            elif isinstance(message, dict):
                message_text = json.dumps(message)
                # logger.debug(f"[WORKER-MSG] Using json.dumps() for dictionary serialization")
            else:
                message_text = str(message)
                # logger.debug(f"[WORKER-MSG] Using str() conversion for serialization")
                
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
                
            # Log message size but not full content to avoid cluttering logs
            msg_size = len(message_text)
            #logger.info(f"[WORKER-MSG] Sending to worker {worker_id}: {log_details} ({msg_size} bytes)")
            
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
    
    async def broadcast_to_clients(self, message: Any) -> int:
        """Broadcast a message to all connected clients"""
        successful_sends = 0
        
        for client_id in list(self.client_connections.keys()):
            if await self.send_to_client(client_id, message):
                successful_sends += 1
        
        return successful_sends
    
    async def broadcast_to_workers(self, message: Any) -> int:
        """Broadcast a message to all connected workers"""
        successful_sends = 0
        
        for worker_id in list(self.worker_connections.keys()):
            if await self.send_to_worker(worker_id, message):
                successful_sends += 1
        
        return successful_sends
    
    async def send_job_update(self, job_id: str, update: Any) -> bool:
        """Send a job update to the subscribed client"""
        try:
            if job_id in self.job_subscriptions:
                client_id = self.job_subscriptions[job_id]
                
                # Verify client connection exists
                if client_id not in self.client_connections:
                    return False
                
                # Send the update to the client
                success = await self.send_to_client(client_id, update)
                return success
            else:
                return False
                
        except Exception as e:
            logger.error(f"[connection_manager.py send_job_update()] Error: {str(e)}")
            return False
    
    async def broadcast_stats(self, stats: Any) -> int:
        """Broadcast stats to monitors only
        
        Args:
            stats: The stats message to broadcast
            
        Returns:
            int: Number of successful sends
        """
        successful_sends = 0
        
        # Check if the stats object already has a type field
        if hasattr(stats, 'type') and stats.type == MessageType.RESPONSE_STATS:
            # This is a legacy ResponseStatsMessage, convert it to a StatsBroadcastMessage
            from .message_models import MessageModels
            message_models = MessageModels()
            
            # Create a minimal StatsBroadcastMessage with just the system field
            connections = {
                "clients": list(self.client_connections.keys()),
                "workers": list(self.worker_connections.keys()),
                "monitors": list(self.monitor_connections.keys())
            }
            
            # Create empty workers dictionary
            workers = {}
            for worker_id, status in self.worker_status.items():
                workers[worker_id] = {"status": status, "connection_status": status}
            
            # Create subscriptions dictionary
            subscriptions = {
                "stats": list(self.stats_subscriptions),
                "job_notifications": list(self.job_notification_subscriptions),
                "jobs": self.job_subscriptions
            }
            
            # Create a proper StatsBroadcastMessage
            stats_message = message_models.create_stats_broadcast_message(
                connections=connections,
                workers=workers,
                subscriptions=subscriptions,
                system=stats.stats if hasattr(stats, 'stats') else {}
            )
        else:
            # Use the message as-is (should be a StatsBroadcastMessage)
            stats_message = stats
        
        # Only send to monitors - regular clients get job-specific updates
        await self.broadcast_to_monitors(stats_message)
        
        return successful_sends
        
    async def broadcast_to_monitors(self, message: Any) -> int:
        """Broadcast a message to all connected monitors"""
        if not self.monitor_connections:
            return 0
            
        # Prepare message for sending
        message_dict = None
        is_pydantic_model = False
        
        # Check if it's a Pydantic model and convert to dict
        if hasattr(message, 'model_dump'):  # Pydantic v2
            message_dict = message.model_dump()
            is_pydantic_model = True
        elif hasattr(message, 'dict'):  # Pydantic v1
            message_dict = message.dict()
            is_pydantic_model = True
        elif isinstance(message, dict):
            message_dict = message.copy()
        else:
            # Create a proper UnknownMessage object for unknown message types
            unknown_msg = UnknownMessage(content=str(message))
            message_dict = unknown_msg.dict() if hasattr(unknown_msg, 'dict') else unknown_msg.model_dump()
            
        # Ensure message has a type
        if "type" not in message_dict:
            # Create a proper UnknownMessage object for messages without a type
            unknown_msg = UnknownMessage(content="No type specified")
            message_dict = unknown_msg.dict() if hasattr(unknown_msg, 'dict') else unknown_msg.model_dump()
            
        # Add timestamp if not present and not a Pydantic model
        if "timestamp" not in message_dict and not is_pydantic_model:
            message_dict["timestamp"] = time.time()
            
        # Add message_id if not present for tracking and not a Pydantic model
        # This prevents adding fields that don't exist in the Pydantic model
        if "message_id" not in message_dict and not is_pydantic_model:
            message_dict["message_id"] = f"{message_dict['type']}-{int(time.time())}"
        
        # Convert to JSON string
        message_json = json.dumps(message_dict)
        
        # Track successful broadcasts
        successful_sends = 0
        skipped_sends = 0
        
        # Get message type for filtering
        message_type = message_dict.get("type", "unknown")
        
        for monitor_id, websocket in list(self.monitor_connections.items()):
            # Check if this monitor has filters and if the message type passes the filter
            filters = self.monitor_filters.get(monitor_id, set())
            
            # If filters exist and message type is not in filters, skip
            if filters and message_type not in filters:
                skipped_sends += 1
                continue
            try:
                # Check if websocket is still open
                if websocket.client_state.name != "CONNECTED":
                    asyncio.create_task(self._schedule_disconnect_monitor(monitor_id))
                    continue
                    
                # Send the message
                await websocket.send_text(message_json)
                successful_sends += 1
                
                # Send an acknowledgment message to confirm successful delivery
                # Using proper AckMessage class instead of raw dictionary
                original_id = message_dict.get("message_id", "unknown")
                ack_message = AckMessage(
                    message_id=f"ack-{int(time.time())}",
                    original_id=original_id,
                    original_type=message_type
                )
                # Convert to dict based on Pydantic version
                ack_dict = ack_message.dict() if hasattr(ack_message, 'dict') else ack_message.model_dump()
                await websocket.send_text(json.dumps(ack_dict))
                
            except RuntimeError as e:
                # Schedule disconnection for websocket errors
                if "WebSocket is not connected" in str(e) or "Connection is closed" in str(e):
                    asyncio.create_task(self._schedule_disconnect_monitor(monitor_id))
            except Exception:
                # Schedule disconnection
                asyncio.create_task(self._schedule_disconnect_monitor(monitor_id))
        

        
        return successful_sends
    
    async def _schedule_disconnect_monitor(self, monitor_id: str) -> None:
        """Schedule monitor disconnection to avoid concurrent modification"""
        self.disconnect_monitor(monitor_id)
        
    async def send_system_status_to_monitors(self, redis_service=None) -> None:
        """Send comprehensive system status to all monitors
        
        Args:
            redis_service: Optional RedisService instance to get detailed worker status
        """
        if not self.monitor_connections:
            return
            
        # Build comprehensive status message using the proper message model
        # Create a dictionary of worker statuses from connection manager's knowledge
        worker_statuses = {}
        for worker_id, status in self.worker_status.items():
            # Check if the worker is subscribed to job notifications AND not disconnected
            is_accepting_jobs = (worker_id in self.job_notification_subscriptions and 
                               status != "disconnected" and 
                               worker_id in self.worker_connections)
            # Get worker capabilities from memory
             # Get worker capabilities from memory
            raw_capabilities = self.worker_capabilities.get(worker_id, {})  # Changed from self.connection_manager.worker_capabilities

            # Parse capabilities using WorkerCapabilities model
            capabilities = WorkerCapabilities(**raw_capabilities)

            capabilities_dict = capabilities.dict()
            
            # Get supported job types
            supported_job_types = capabilities_dict.get("supported_job_types", [])
            #logger.info(f"[MONITOR-STATUS] Worker {worker_id} capabilities from memory: {capabilities}")
            
            # Check if supported_job_types is a string (JSON) that needs parsing
            if isinstance(supported_job_types, str):
                try:
                    #logger.info(f"[MONITOR-STATUS] Worker {worker_id} has supported_job_types as string: {supported_job_types}")
                    parsed_job_types = json.loads(supported_job_types)
                    #logger.info(f"[MONITOR-STATUS] Parsed job types from JSON string: {parsed_job_types}")
                    supported_job_types = parsed_job_types
                except json.JSONDecodeError as e:
                    logger.error(f"[MONITOR-STATUS] Error parsing job types JSON for worker {worker_id}: {e}")
            
            worker_statuses[worker_id] = {
                "status": status, 
                "connection_status": status,
                "is_accepting_jobs": is_accepting_jobs,  # Add field to show if worker is accepting jobs
                "capabilities": capabilities_dict,
                "supported_job_types": supported_job_types
            }
            
            #logger.info(f"[MONITOR-STATUS] Worker {worker_id} status prepared: {worker_statuses[worker_id]}")
        
        # Ensure all connected workers have at least a basic status entry
        for worker_id in self.worker_connections.keys():
            if worker_id not in worker_statuses:
                # Check if the worker is subscribed to job notifications AND connected
                is_accepting_jobs = (worker_id in self.job_notification_subscriptions and 
                                   worker_id in self.worker_connections)
                # Get worker capabilities from memory
                raw_capabilities = self.worker_capabilities.get(worker_id, {})  # Changed from self.connection_manager.worker_capabilities

                # Parse capabilities using WorkerCapabilities model
                capabilities = WorkerCapabilities(**raw_capabilities)

                capabilities_dict = capabilities.dict()
                #logger.info(f"[MONITOR-STATUS] Worker {worker_id} capabilities from memory (fallback): {capabilities}")
                
                # Get supported job types
                supported_job_types = capabilities_dict.get("supported_job_types", [])
                
                if isinstance(supported_job_types, str):
                    try:
                        #logger.info(f"[MONITOR-STATUS] Worker {worker_id} has supported_job_types as string (fallback): {supported_job_types}")
                        parsed_job_types = json.loads(supported_job_types)
                        #logger.info(f"[MONITOR-STATUS] Parsed job types from JSON string (fallback): {parsed_job_types}")
                        supported_job_types = parsed_job_types
                    except json.JSONDecodeError as e:
                        logger.error(f"[MONITOR-STATUS] Error parsing job types JSON for worker {worker_id} (fallback): {e}")
                
                worker_statuses[worker_id] = {
                    "status": "connected",
                    "connection_status": "connected",
                    "is_accepting_jobs": is_accepting_jobs,  # Add field to show if worker is accepting jobs
                    "capabilities": capabilities_dict,
                    "supported_job_types": supported_job_types
                }
                
                #logger.info(f"[MONITOR-STATUS] Worker {worker_id} status prepared (fallback): {worker_statuses[worker_id]}")
        
        # Create connections dictionary
        connections = {
            "clients": list(self.client_connections.keys()),
            "workers": list(self.worker_connections.keys()),
            "monitors": list(self.monitor_connections.keys())
        }
        
        # Create subscriptions dictionary
        subscriptions = {
            "stats": list(self.stats_subscriptions),
            "job_notifications": list(self.job_notification_subscriptions),
            "jobs": self.job_subscriptions
        }
        
        # Log the basic status structure
        worker_count = len(worker_statuses) if worker_statuses else 0
        print(f"🔄 Created system status with {worker_count} workers")
        
        # Safely access connection counts
        client_count = len(connections.get('clients', []))
        worker_count = len(connections.get('workers', []))
        monitor_count = len(connections.get('monitors', []))
        print(f"🔄 Connections: {client_count} clients, {worker_count} workers, {monitor_count} monitors")
        
        # Initialize system stats with basic information
        system_stats = {
            "queues": {"priority": 0, "standard": 0, "total": 0},
            "jobs": {"total": 0, "status": {}},
            "workers": {"total": worker_count, "status": {}}
        }
        
        # Add detailed worker status from Redis if available
        if redis_service:
            try:
                # Get detailed worker status from Redis
                print(f"🔄 Fetching detailed worker status from Redis service")
                redis_workers_status = redis_service.get_all_workers_status()
                
                # Update the workers section with detailed information
                detailed_workers = worker_statuses.copy()  # Start with our basic status info
                
                for worker_id, worker_data in redis_workers_status.items():
                    # If we already have this worker, update with Redis data
                    if worker_id in detailed_workers:
                        # Preserve connection_status from our basic info
                        connection_status = detailed_workers[worker_id].get("connection_status", "unknown")
                        # Update with Redis data
                        detailed_workers[worker_id].update(worker_data)
                        # Make sure connection_status is preserved
                        detailed_workers[worker_id]["connection_status"] = connection_status
                    else:
                        # New worker from Redis that we didn't know about
                        worker_info = worker_data.copy()
                        worker_info["connection_status"] = "disconnected"  # Not in our connections
                        detailed_workers[worker_id] = worker_info
                
                # Update the workers dictionary
                worker_statuses = detailed_workers
                
                # Add system stats
                redis_stats = redis_service.request_stats()
                if redis_stats:
                    # Update our basic stats with Redis data
                    system_stats.update(redis_stats)
                    # Make sure worker count is correct
                    if "workers" in system_stats and isinstance(system_stats["workers"], dict):
                        system_stats["workers"]["total"] = worker_count
                
            except Exception as e:
                print(f"Error getting detailed worker status: {e}")
                # Continue with basic stats if Redis fails
        
        # Import message models here to avoid circular imports
        from .message_models import MessageModels
        message_models = MessageModels()
        
        # Create the status broadcast message using the factory method
        status_message = message_models.create_stats_broadcast_message(
            connections=connections,
            workers=worker_statuses,
            subscriptions=subscriptions,
            system=system_stats
        )
        
        # Broadcast to all monitors
        sent_count = await self.broadcast_to_monitors(status_message)
        
    def subscribe_worker_to_job_notifications(self, worker_id: str) -> None:
        """Subscribe a worker to job notifications"""
        self.job_notification_subscriptions.add(worker_id)
    
    def unsubscribe_worker_from_job_notifications(self, worker_id: str) -> None:
        """Unsubscribe a worker from job notifications"""
        if worker_id in self.job_notification_subscriptions:
            self.job_notification_subscriptions.remove(worker_id)
    
    async def update_worker_status(self, worker_id: str, status: str) -> None:
        """Update a worker's status and broadcast to monitors"""
        if worker_id in self.worker_connections:
            # Update status in memory
            self.worker_status[worker_id] = status
            
            # Create worker status update message using the proper message model
            status_update = WorkerStatusMessage(
                type=MessageType.WORKER_STATUS,
                timestamp=time.time(),
                message_id=f"worker-status-{int(time.time())}",
                worker_id=worker_id,
                status=status
            )
            
            # Broadcast to all monitors
            await self.broadcast_to_monitors(status_update)
    
    async def notify_idle_workers(self, job_notification: Any) -> int:
        """Send job notification to idle workers subscribed to notifications"""
        # Log the start of the notification process
        logger.debug(f"[JOB-NOTIFY] Starting job notification broadcast process")
        successful_sends = 0
        
        # Convert Pydantic model to dict if needed
        if hasattr(job_notification, 'dict'):
            # It's a Pydantic model, convert to dict
            notification_dict = job_notification.dict()
            logger.debug(f"[JOB-NOTIFY] Converted Pydantic model to dict")
        else:
            # It's already a dict
            notification_dict = job_notification
            logger.debug(f"[JOB-NOTIFY] Using existing dict notification")
            
        job_id = notification_dict.get('job_id', 'unknown')
        job_type = notification_dict.get('job_type', 'unknown')
        
        logger.info(f"[JOB-NOTIFY] Broadcasting job notification - ID: {job_id}, Type: {job_type}")
        
        # Ensure the notification has the correct type
        if 'type' not in notification_dict:
            notification_dict['type'] = 'job_available'
            logger.debug(f"[JOB-NOTIFY] Added missing type field: 'job_available'")
        
        # Log the subscription state
        logger.debug(f"[JOB-NOTIFY] Total subscribed workers: {len(self.job_notification_subscriptions)}")
        if self.job_notification_subscriptions:
            logger.debug(f"[JOB-NOTIFY] Subscribed workers: {list(self.job_notification_subscriptions)}")
        
        # Find eligible idle workers - must be subscribed, idle, and connected
        idle_workers = []
        for worker_id in list(self.job_notification_subscriptions):
            worker_status = self.worker_status.get(worker_id, "unknown")
            # Only consider workers that are both idle AND connected
            if (worker_id in self.worker_status and 
                worker_status == "idle" and 
                worker_id in self.worker_connections):
                idle_workers.append(worker_id)
                logger.debug(f"[JOB-NOTIFY] Worker {worker_id} is idle and eligible for notification")
            else:
                # Log more detailed reason for ineligibility
                if worker_id not in self.worker_status:
                    reason = "not in worker_status"
                elif worker_status != "idle":
                    reason = f"status is {worker_status}"
                elif worker_id not in self.worker_connections:
                    reason = "not connected"
                else:
                    reason = "unknown reason"
                logger.debug(f"[JOB-NOTIFY] Worker {worker_id} is not eligible - {reason}")
        
        if not idle_workers:
            logger.debug(f"[JOB-NOTIFY] No idle workers found to notify")
            return 0
        
        logger.debug(f"[JOB-NOTIFY] Found {len(idle_workers)} idle workers to notify")
        
        # Check that workers are actually connected
        connected_count = 0
        for worker_id in idle_workers.copy():
            if worker_id not in self.worker_connections:
                logger.debug(f"[JOB-NOTIFY] Worker {worker_id} is not connected, removing from notification list")
                idle_workers.remove(worker_id)
            else:
                connected_count += 1
        
        logger.debug(f"[JOB-NOTIFY] {connected_count} workers are connected and will receive notifications")
        
        # Create a copy of the notification for each worker to avoid shared references
        # This ensures each worker gets its own notification with accurate worker count
        base_notification = notification_dict.copy()
        
        # Send to eligible workers
        excluded_workers = []
        
        for worker_id in idle_workers:
            # Check if worker has previously failed this job
            # This is the in-memory approach to prevent reassigning failed jobs
            if worker_id in self.worker_failed_jobs and job_id in self.worker_failed_jobs[worker_id]:
                logger.info(f"""[connection_manager.py notify_idle_workers()]
╔══════════════════════════════════════════════════════════════════════════════╗
║ WORKER EXCLUDED FROM JOB NOTIFICATION                                        ║
║ Worker ID: {worker_id}                                                       ║
║ Job ID: {job_id}                                                             ║
║ Reason: Worker previously failed this job                                     ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
                excluded_workers.append(worker_id)
                continue
                
            # Create a worker-specific notification with accurate worker count
            worker_notification = base_notification.copy()
            # If this is a worker_notification type message, ensure worker_count is correct
            if worker_notification.get('type') == 'worker_notification':
                worker_notification['worker_count'] = len(idle_workers)
                logger.debug(f"[JOB-NOTIFY] Updated worker_count to {len(idle_workers)} for worker {worker_id}")
            
            # Check worker capabilities for job type
            raw_capabilities = self.worker_capabilities.get(worker_id, {})  # Changed from self.connection_manager.worker_capabilities

            # Parse capabilities using WorkerCapabilities model
            capabilities = WorkerCapabilities(**raw_capabilities)

            capabilities_dict = capabilities.dict()
            
            # Get supported job types
            supported_job_types = capabilities_dict.get("supported_job_types", [])
            
            if job_type in supported_job_types:
                logger.info(f"[JOB-NOTIFY] Worker {worker_id} supports job type {job_type}, sending notification")
                success = await self.send_to_worker(worker_id, worker_notification)
                if success:
                    logger.info(f"[JOB-NOTIFY] Successfully sent notification to worker {worker_id}")
                    successful_sends += 1
                else:
                    logger.warning(f"[JOB-NOTIFY] Failed to send notification to worker {worker_id}")
            else:
                logger.warning(f"[JOB-NOTIFY] Worker {worker_id} does not support job type {job_type}, skipping notification")
                logger.info(f"[JOB-NOTIFY] Worker {worker_id} capabilities: {capabilities}")
                
        # Log summary of excluded workers
        if excluded_workers:
            logger.info(f"""[connection_manager.py notify_idle_workers()]
╔══════════════════════════════════════════════════════════════════════════════╗
║ WORKER EXCLUSION SUMMARY                                                    ║
║ Job ID: {job_id}                                                             ║
║ Excluded Workers: {len(excluded_workers)}                                     ║
║ Remaining Eligible Workers: {len(idle_workers) - len(excluded_workers)}       ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
        return successful_sends
    
    async def broadcast_job_notification(self, job_notification: BaseMessage) -> int:
        """Broadcast job notification to subscribed clients and all monitors
        
        Args:
            job_notification: The notification to broadcast as a BaseMessage object
            
        Returns:
            int: Number of successful sends
        """
        # Note: This method now only accepts BaseMessage objects to ensure type consistency
        # All message objects in the system should inherit from BaseMessage
        successful_sends = 0
        client_id = None
        
        # Send job completion notifications to subscribed clients
        if hasattr(job_notification, 'job_id'):
            job_id = job_notification.job_id
            
            # Check if any client is subscribed to this job
            if job_id in self.job_subscriptions:
                client_id = self.job_subscriptions[job_id]
                
                # Send the notification to the subscribed client
                logger.debug(f"[JOB-NOTIFY] Sending job notification to subscribed client {client_id} for job {job_id}")
                if await self.send_to_client(client_id, job_notification):
                    successful_sends += 1
                    logger.debug(f"[JOB-NOTIFY] Successfully sent job notification to client {client_id}")
                else:
                    logger.debug(f"[JOB-NOTIFY] Failed to send job notification to client {client_id}")
            else:
                logger.debug(f"[JOB-NOTIFY] No clients subscribed to job {job_id}, skipping client notification")
                
            # Forward to all monitors regardless of client subscription status
            if self.monitor_connections:
                # Create a copy of the notification with client_id added
                # We need to convert to dict first to add the client_id field
                if hasattr(job_notification, 'model_dump'):
                    # Pydantic v2
                    notification_dict = job_notification.model_dump()
                elif hasattr(job_notification, 'dict'):
                    # Pydantic v1
                    notification_dict = job_notification.dict()
                else:
                    # Fallback
                    notification_dict = {"job_id": job_id}
                    if hasattr(job_notification, "result"):
                        notification_dict["result"] = job_notification.result
                    if hasattr(job_notification, "message"):
                        notification_dict["message"] = job_notification.message
                
                # Add client_id to the message for monitors
                notification_dict["client_id"] = client_id
                
                # Send to all monitors
                monitor_count = 0
                for monitor_id, websocket in list(self.monitor_connections.items()):
                    try:
                        await websocket.send_text(json.dumps(notification_dict))
                        monitor_count += 1
                        successful_sends += 1
                    except Exception as e:
                        logger.warning(f"[JOB-NOTIFY] Failed to send to monitor {monitor_id}: {str(e)}")
                
                if monitor_count > 0:
                    logger.debug(f"[JOB-NOTIFY] Forwarded job notification for job {job_id} to {monitor_count} monitors")
        else:
            logger.warning(f"[JOB-NOTIFY] Job notification missing job_id attribute, cannot route to subscribers")
        
        return successful_sends
        
    async def forward_job_progress(self, progress_message: BaseMessage) -> bool:
        """Forward job progress update from a worker to the subscribed client and all monitors
        
        Args:
            progress_message: The job progress update message (UpdateJobProgressMessage)
            
        Returns:
            bool: True if the update was successfully forwarded, False otherwise
        """
        try:
            logger.debug(f"[connection_manager.py forward_job_progress()] Forwarding progress update: {progress_message}")
            # Extract job_id from the message
            if not hasattr(progress_message, 'job_id'):
                logger.warning(f"[connection_manager.py forward_job_progress()] Message does not contain job_id: {progress_message}")
                return False
                
            job_id = progress_message.job_id
            client_id = None
            client_success = False
            
            # Check if any client is subscribed to this job
            if job_id in self.job_subscriptions:
                # Get the client ID subscribed to this job
                client_id = self.job_subscriptions[job_id]
                
                # Check if the client is still connected
                if client_id not in self.client_connections:
                    #logger.warning(f"[connection_manager.py forward_job_progress 4] Client {client_id} subscribed to job {job_id} is no longer connected")
                    # Remove the subscription
                    del self.job_subscriptions[job_id]
                else:
                    # Forward the progress update directly to the client
                    # We use the same message format (UpdateJobProgressMessage) for consistency
                    client_success = await self.send_to_client(client_id, progress_message)
                    
                    if not client_success:
                        logger.warning(f"[connection_manager.py forward_job_progress()] Failed to forward progress update for job {job_id} to client {client_id}")
            else:
                logger.debug(f"[connection_manager.py forward_job_progress 3] No clients subscribed to job {job_id}")
            
            # Forward to all monitors regardless of client subscription status
            monitor_success = False
            if self.monitor_connections:
                # Create a copy of the progress message with client_id added
                # We need to convert to dict first to add the client_id field
                if hasattr(progress_message, 'model_dump'):
                    # Pydantic v2
                    progress_dict = progress_message.model_dump()
                elif hasattr(progress_message, 'dict'):
                    # Pydantic v1
                    progress_dict = progress_message.dict()
                else:
                    # Fallback
                    progress_dict = {"job_id": job_id}
                    if hasattr(progress_message, "progress"):
                        progress_dict["progress"] = progress_message.progress
                    if hasattr(progress_message, "message"):
                        progress_dict["message"] = progress_message.message
                
                # Add client_id to the message for monitors
                progress_dict["client_id"] = client_id
                
                # Send to all monitors
                monitor_count = 0
                for monitor_id, websocket in list(self.monitor_connections.items()):
                    try:
                        await websocket.send_text(json.dumps(progress_dict))
                        monitor_count += 1
                    except Exception as e:
                        logger.warning(f"[connection_manager.py forward_job_progress] Failed to send to monitor {monitor_id}: {str(e)}")
                
                monitor_success = monitor_count > 0
                # if monitor_success:
                #     logger.debug(f"[JOB-PROGRESS] Forwarded progress update for job {job_id} to {monitor_count} monitors")
            
            # Return true if either client or monitor forwarding was successful
            return client_success or monitor_success
            
        except Exception as e:
            logger.error(f"[connection_manager.py forward_job_progress 5] Error forwarding job progress update: {str(e)}")
            return False
            
    async def forward_job_completion(self, job_id: str, complete_message: Dict[str, Any]) -> bool:
        """
        Forward job completion message to the subscribed client and all monitors
        
        Args:
            job_id: The ID of the completed job
            complete_message: The job completion message to forward
            
        Returns:
            bool: True if the message was successfully forwarded, False otherwise
        """
        try:
            logger.info(f"[2025-05-20T23:30:00-04:00] Forwarding job completion message for job {job_id}")
            
            client_id = None
            client_success = False
            
            # Check if any client is subscribed to this job
            if job_id in self.job_subscriptions:
                # Get the client ID subscribed to this job
                client_id = self.job_subscriptions[job_id]
                
                # Check if the client is still connected
                if client_id not in self.client_connections:
                    logger.warning(f"[2025-05-20T23:30:00-04:00] Client {client_id} subscribed to job {job_id} is no longer connected")
                    # Remove the subscription
                    del self.job_subscriptions[job_id]
                else:
                    # Forward the completion message directly to the client
                    logger.info(f"[2025-05-20T23:30:00-04:00] Sending complete_job message to client {client_id} for job {job_id}")
                    client_success = await self.send_to_client(client_id, complete_message)
                    
                    if not client_success:
                        logger.warning(f"[2025-05-20T23:30:00-04:00] Failed to forward completion message for job {job_id} to client {client_id}")
            else:
                logger.debug(f"[2025-05-20T23:30:00-04:00] No clients subscribed to job {job_id}")
            
            # Forward to all monitors regardless of client subscription status
            monitor_success = False
            if self.monitor_connections:
                # Add client_id to the message for monitors
                monitor_message = complete_message.copy()
                monitor_message["client_id"] = client_id
                
                # Send to all monitors
                monitor_count = 0
                for monitor_id, websocket in list(self.monitor_connections.items()):
                    try:
                        await websocket.send_text(json.dumps(monitor_message))
                        monitor_count += 1
                    except Exception as e:
                        logger.warning(f"[2025-05-20T23:30:00-04:00] Failed to send completion message to monitor {monitor_id}: {str(e)}")
                
                monitor_success = monitor_count > 0
                if monitor_success:
                    logger.info(f"[2025-05-20T23:30:00-04:00] Forwarded completion message for job {job_id} to {monitor_count} monitors")
            
            # Return true if either client or monitor forwarding was successful
            return client_success or monitor_success
            
        except Exception as e:
            logger.error(f"[2025-05-20T23:30:00-04:00] Error forwarding job completion message: {str(e)}")
            logger.exception("Complete stack trace:")
            return False
    
    async def forward_connector_ws_status(self, status_message: BaseMessage) -> bool:
        """Forward connector WebSocket status message to all monitors
        
        This method forwards connector WebSocket status messages to all connected monitors.
        It's used for real-time monitoring of connector WebSocket connections to external services.
        
        Args:
            status_message: The connector WebSocket status message (ConnectorWebSocketStatusMessage)
            
        Returns:
            bool: True if the status was successfully forwarded to at least one monitor, False otherwise
        """
        try:
            logger.debug(f"[connection_manager.py forward_connector_ws_status] Forwarding connector WS status: {status_message}")
            
            # If there are no monitors connected, log and return
            if not self.monitor_connections:
                logger.debug(f"[connection_manager.py forward_connector_ws_status] No monitors connected, skipping status update")
                return False
            
            # Track successful sends
            successful_sends = 0
            
            # Forward the status message to all connected monitors
            for monitor_id, websocket in self.monitor_connections.items():
                try:
                    # Send the message to the monitor
                    await websocket.send_text(status_message.model_dump_json())
                    successful_sends += 1
                except Exception as e:
                    logger.warning(f"[connection_manager.py forward_connector_ws_status] Failed to send status update to monitor {monitor_id}: {str(e)}")
            
            # Return success if at least one monitor received the update
            return successful_sends > 0
            
        except Exception as e:
            logger.error(f"[connection_manager.py forward_connector_ws_status] Error forwarding connector WS status: {str(e)}")
            return False
        
    def set_monitor_subscriptions(self, monitor_id: str, channels: List[str]) -> None:
        """Set the subscription channels for a monitor
        
        Args:
            monitor_id: The ID of the monitor to set subscriptions for
            channels: List of channel names to subscribe to
        """
        # Check if monitor is connected
        if monitor_id not in self.monitor_connections:
            return
        else:
            print(f"🔍 No previous subscriptions")
            #logger.info(f"[MONITOR-SUB] Monitor {monitor_id} setting initial subscriptions to {channels}")
            
        # Update the monitor's filter set
        self.monitor_filters[monitor_id] = set(channels)
        
        # Log the subscription update
        print(f"🔍 Successfully updated subscriptions for monitor {monitor_id} ✅")
        print(f"🔍 Subscribed to channels: {channels}")
        #logger.info(f"[MONITOR-SUB] Monitor {monitor_id} subscribed to channels: {channels}")
        
        # Send confirmation message to the monitor
        try:
            # Using proper SubscriptionConfirmedMessage class instead of raw dictionary
            # Note: We need to adapt the SubscriptionConfirmedMessage to include monitor_id and channels
            # Since our model only has job_id, we'll add these as additional fields
            confirmation = SubscriptionConfirmedMessage(
                job_id="monitor-subscription",  # Using a placeholder since this isn't for a specific job
                monitor_id=monitor_id,
                channels=channels
            )
            
            print(f"🔍 Sending confirmation message to monitor...")
            # Create a task to send the confirmation asynchronously
            websocket = self.monitor_connections[monitor_id]
            # Convert to dict based on Pydantic version
            confirmation_dict = confirmation.dict() if hasattr(confirmation, 'dict') else confirmation.model_dump()
            asyncio.create_task(websocket.send_text(json.dumps(confirmation_dict)))
            
            print(f"🔍 Confirmation message sent successfully ✅")
            #logger.info(f"[MONITOR-SUB] Sent subscription confirmation to monitor {monitor_id}")
            
            # Send an immediate system status update to the monitor
            print(f"🔍 Scheduling immediate system status update for monitor...")
            asyncio.create_task(self.send_system_status_to_monitors())
            print(f"🔍 System status update scheduled ✅")
            #logger.info(f"[MONITOR-SUB] Scheduled immediate system status update for monitor {monitor_id}")
            
        except Exception as e:
            print(f"🔍 ERROR sending confirmation to monitor: {str(e)} ❌")
            logger.error(f"[MONITOR-SUB] Error sending subscription confirmation to monitor {monitor_id}: {str(e)}")
            import traceback
            traceback.print_exc()
            
        print(f"🔍🔍🔍 END MONITOR SUBSCRIPTION REQUEST 🔍🔍🔍\n\n")
    
    async def _close_websocket(self, websocket: WebSocket, reason: str) -> None:
        """Gracefully close a WebSocket connection with error handling
        
        Args:
            websocket: The WebSocket connection to close
            reason: The reason for closing the connection
        """
        try:
            logger.debug(f"Attempting to close WebSocket connection: {reason}")
            # Use a standard WebSocket close code (1000 = normal closure)
            await websocket.close(code=1000, reason=reason)
            logger.info(f"WebSocket connection closed successfully: {reason}")
        except RuntimeError as e:
            # Handle specific runtime errors like "WebSocket is not connected"
            if "WebSocket is not connected" in str(e) or "Connection is closed" in str(e):
                logger.debug(f"WebSocket already closed: {reason}")
            else:
                logger.warning(f"Runtime error while closing WebSocket: {str(e)}")
        except Exception as e:
            # Handle any other unexpected errors
            logger.warning(f"Error while closing WebSocket: {str(e)}, type: {type(e).__name__}")
    
    async def notify_job_update(self, job_id: str, update: Dict[str, Any]) -> bool:
        """Notify subscribers about a job update.
        
        Args:
            job_id: ID of the job that was updated
            update: Update data
            
        Returns:
            bool: True if update was sent successfully, False otherwise
        """
        # Similar implementation to send_job_update
        try:
            # Check if any clients are subscribed to this job
            if job_id not in self.job_subscriptions:
                logger.debug(f"[JOB-UPDATE] No clients subscribed to job {job_id}")
                return False
                
            # Get the client ID subscribed to this job
            client_id = self.job_subscriptions[job_id]
            
            # Check if the client is still connected
            if client_id not in self.client_connections:
                logger.warning(f"[JOB-UPDATE] Client {client_id} subscribed to job {job_id} is no longer connected")
                # Remove the subscription
                del self.job_subscriptions[job_id]
                return False
            
            # Send the update to the client
            websocket = self.client_connections[client_id]
            await websocket.send_text(json.dumps(update))
            logger.info(f"[JOB-UPDATE] Sent job update for {job_id} to client {client_id}")
            return True
            
        except Exception as e:
            logger.error(f"[JOB-UPDATE] Error sending job update for {job_id}: {str(e)}")
            return False
    
    async def send_to_monitor(self, monitor_id: str, message: BaseMessage) -> bool:
        """Send a message to a specific monitor.
        
        Args:
            monitor_id: ID of the monitor to send the message to
            message: Message to send
            
        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        try:
            # Check if the monitor is connected
            if monitor_id not in self.monitor_connections:
                logger.warning(f"[MONITOR-MSG] Monitor {monitor_id} is not connected")
                return False
            
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
