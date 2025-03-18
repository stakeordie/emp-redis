#!/usr/bin/env python3
# Implementation of the MessageHandlerInterface
import asyncio
import json
import time
import uuid
from typing import Dict, Any, Optional, Callable, Awaitable, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosedError

from .interfaces.message_handler_interface import MessageHandlerInterface
from .redis_service import RedisService
from .connection_manager import ConnectionManager
from .message_router import MessageRouter
from .core_types.base_messages import BaseMessage
from .message_models import (
    MessageModels, ErrorMessage, 
    JobAcceptedMessage, WorkerRegisteredMessage,
    JobAvailableMessage, RegisterWorkerMessage, 
    UpdateJobProgressMessage, CompleteJobMessage, 
    WorkerHeartbeatMessage, WorkerStatusMessage, 
    ClaimJobMessage, ClaimJobMessage, 
    JobAssignedMessage, SubscriptionConfirmedMessage,
    AckMessage, JobNotificationsSubscribedMessage,
    ResponseJobStatusMessage
    # SubscribeJobNotificationsMessage has been removed - functionality now in RegisterWorkerMessage
)
from .utils.logger import logger

# Module-level print to verify this file is being loaded
# print("\n\n==== MESSAGE_HANDLER.PY MODULE LOADED ====\n\n")

class MessageHandler(MessageHandlerInterface):
    """
    Implementation of the MessageHandlerInterface.
    
    This class provides a concrete implementation of the message handling
    contract defined in the interface, organizing and maintaining
    message handling logic for the application.
    """
    
    def __init__(self, redis_service: RedisService, connection_manager: ConnectionManager,
                 message_router: MessageRouter, message_models: MessageModels):
        """
        Initialize the message handler with required services.
        
        Args:
            redis_service: Redis service instance
            connection_manager: Connection manager instance
            message_router: Message router instance
            message_models: Message models instance
        """
        # Store dependencies as instance variables
        self.redis_service: RedisService = redis_service
        self.connection_manager: ConnectionManager = connection_manager
        self.message_router: MessageRouter = message_router
        self.message_models: MessageModels = message_models
        self._background_tasks: List[asyncio.Task] = []
    
    # init_connections method removed as it's now handled by the ConnectionManager directly
    
    async def start_background_tasks(self) -> None:
        """
        Start background tasks for the application.
        
        This method initializes and starts any background tasks
        needed for the application, such as periodic stats broadcasts,
        cleanup tasks, etc.
        """
        # Start the background tasks
        self._background_tasks.append(asyncio.create_task(self._broadcast_stats_task()))
        self._background_tasks.append(asyncio.create_task(self._cleanup_stale_claims_task()))
        self._background_tasks.append(asyncio.create_task(self._mark_stale_workers_task()))
        self._background_tasks.append(asyncio.create_task(self._monitor_status_update_task()))
        self._background_tasks.append(asyncio.create_task(self._start_redis_listener()))
        
        # logger.info("Started all background tasks")
    
    async def stop_background_tasks(self) -> None:
        """
        Stop background tasks for the application.
        
        This method properly stops and cleans up any background
        tasks started by the application.
        """
        # Cancel all background tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()
                
        # Wait for all tasks to complete their cancellation
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            
        # Clear the task list
        self._background_tasks.clear()
        
        # logger.info("Stopped all background tasks")
    
    async def handle_client_message(self, client_id: str, 
                                  message_type: str,
                                  message_data: Dict[str, Any], 
                                  websocket: WebSocket) -> None:
        """
        Handle a message from a client.
        
        Args:
            client_id: Client identifier
            message_type: Type of message
            message_data: Message data
            websocket: WebSocket connection
        """
        # Process message based on type using match-case
        match message_type:
            case "submit_job":
                # Pass the dictionary directly to match the method signature
                # This ensures type compatibility with the interface
                await self.handle_submit_job(client_id, message_data)
            case "request_job_status":
                job_id = message_data.get("job_id")
                if job_id:
                    # Get job status from Redis
                    job_data = self.redis_service.get_job_status(job_id)
                    
                    if not job_data:
                        error_message = ErrorMessage(error=f"Job {job_id} not found")
                        await self.connection_manager.send_to_client(client_id, error_message)
                        return
                    
                    # Create response using the new ResponseJobStatusMessage class
                    response = ResponseJobStatusMessage(
                        job_id=job_id,
                        status=job_data.get("status", "unknown"),
                        progress=int(job_data.get("progress", 0)) if "progress" in job_data else None,
                        worker_id=job_data.get("worker"),
                        started_at=float(job_data["started_at"]) if "started_at" in job_data else None,
                        completed_at=float(job_data["completed_at"]) if "completed_at" in job_data else None,
                        result=job_data.get("result"),
                        message=job_data.get("message")
                    )
                    await self.connection_manager.send_to_client(client_id, response)
                    
                    # Subscribe client to future updates for this job
                    await self.connection_manager.subscribe_to_job(job_id, client_id)
                else:
                    error_message = ErrorMessage(error="Missing job_id in request_job_status request")
                    await self.connection_manager.send_to_client(client_id, error_message)
            case "subscribe_job":
                job_id = message_data.get("job_id")
                if job_id:
                    await self.connection_manager.subscribe_to_job(job_id, client_id)
                    # Use SubscriptionConfirmedMessage for consistency
                    confirmation = SubscriptionConfirmedMessage(job_id=job_id)
                    await websocket.send_text(confirmation.model_dump_json())
                else:
                    error_message = ErrorMessage(error="Missing job_id in subscribe_job request")
                    await self.connection_manager.send_to_client(client_id, error_message)
            case "subscribe_stats":
                self.handle_subscribe_stats(client_id)
                # Use SubscriptionConfirmedMessage for consistency
                # Note: SubscriptionConfirmedMessage requires job_id parameter, using 'stats' as a special identifier
                # for stats subscriptions, with channels=['stats'] to indicate the subscription type
                confirmation = SubscriptionConfirmedMessage(job_id="stats", channels=["stats"])
                await websocket.send_text(confirmation.model_dump_json())
            case "request_stats":
                # Extract message_id if present
                message_id = message_data.get('message_id', None)
                # Pass the original message for context
                await self.handle_request_stats(client_id, message_id, message_data)
            case "stay_alive":
                # Respond with a simple acknowledgment
                # WebSocket protocol handles connection keepalive automatically
                response = {"type": "acknowledgment", "timestamp": time.time()}
                await websocket.send_text(json.dumps(response))
            case _:
                # Handle unrecognized message type
                error_message = ErrorMessage(error=f"Unsupported message type: {message_type}")
                await self.connection_manager.send_to_client(client_id, error_message)
            
    async def handle_submit_job(self, client_id: str, message: Dict[str, Any]) -> None:
        """
        Handle job submission from a client.
        
        Args:
            client_id: Client identifier
            message: Job submission message
        """
        # Generate job ID if not provided
        job_id = f"job-{uuid.uuid4()}"
        
        # Extract data directly from the message dictionary
        # Using .get() with default values to handle missing keys
        job_type = message.get('job_type', 'unknown')
        priority = message.get('priority', 0)
        payload = message.get('payload', {})
        
        # Add detailed comment explaining type handling
        # We're using dictionary access instead of attribute access because
        # the method signature expects Dict[str, Any] rather than SubmitJobMessage
        
        # Add job to Redis
        job_data = self.redis_service.add_job(
            job_id=job_id,
            job_type=job_type,
            priority=priority,
            job_request_payload=payload,
            client_id=client_id
        )
        
        # Send confirmation response
        # Note: We're not directly notifying workers here anymore
        # Worker notification will happen through broadcast_pending_jobs_to_idle_workers
        response = JobAcceptedMessage(
            job_id=job_id,
            position=job_data.get("position", -1),
            notified_workers=0  # Default to 0 since we're not directly notifying workers
        )
        
        await self.connection_manager.send_to_client(client_id, response)
        # Automatically subscribe client to job updates
        await self.connection_manager.subscribe_to_job(client_id, job_id)
        
        # Broadcast pending jobs to idle workers
        # This ensures that when a new job is submitted, we check for idle workers
        # and broadcast the job to them using our improved broadcasting mechanism
        await self.broadcast_pending_jobs_to_idle_workers()
    
    # The handle_get_job_status method has been removed and replaced with direct handling
    # of request_job_status messages in the handle_message method
    
    def handle_subscribe_stats(self, client_id: str) -> None:
        """
        Handle stats subscription request from a client.
        
        Args:
            client_id: Client identifier
        """
        self.connection_manager.subscribe_to_stats(client_id)
    
    def _serialize_stats(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ensure all values in the stats dictionary are JSON serializable.
        
        Args:
            stats: Raw stats dictionary from Redis service
            
        Returns:
            Dict[str, Any]: Serialized stats dictionary with JSON-compatible values
        """
        # Use json module with a custom encoder to handle non-serializable types
        class CustomEncoder(json.JSONEncoder):
            def default(self, obj) -> str:
                # Convert any non-serializable object to a string
                return str(obj)
        
        try:
            # Convert to JSON and back to handle serialization
            # This automatically handles nested structures and non-serializable types
            json_str = json.dumps(stats, cls=CustomEncoder)
            # Explicitly type the return value to match the function's return type
            serialized_stats: Dict[str, Any] = json.loads(json_str)
            return serialized_stats
        except Exception as e:
            # In case of any serialization error, log it and return a simplified version
            logger.error(f"Error serializing stats: {str(e)}")
            # Explicitly type the return value to match the function's return type
            error_response: Dict[str, Any] = {"error": f"Failed to serialize stats: {str(e)}", "partial_data": str(stats)[:1000]}
            return error_response
    
    async def handle_request_stats(self, client_id: str, message_id: Optional[str] = None, original_message: Optional[Dict] = None) -> None:
        """
        Handle stats request from a monitor.
        
        This method is restricted to monitor clients only. Regular clients should use
        handle_get_job_status for job-specific information.
        
        Args:
            client_id: Client identifier
            message_id: Optional message ID for acknowledgment
            original_message: Optional original message for context
        """
        try:
            # Check if client is a monitor
            if client_id not in self.connection_manager.monitor_connections:
                # Send error message if not a monitor
                error_message = ErrorMessage(error="Stats requests are restricted to monitors only")
                await self.connection_manager.send_to_client(client_id, error_message)
                return
                
            # Get the stats from Redis service
            stats = self.redis_service.request_stats()
            
            # Serialize the stats to ensure JSON compatibility
            serializable_stats = self._serialize_stats(stats)
            
            # Create a proper StatsResponseMessage object with serializable stats
            stats_response = self.message_models.create_response_stats_message(serializable_stats)      
            # Send the response to the client
            await self.connection_manager.send_to_client(client_id, stats_response)
            
            # Send acknowledgment if message_id is provided
            if message_id and original_message:
                ack_message = AckMessage(
                    original_id=message_id,
                    original_type=original_message.get('type', 'request_stats')
                )
                await self.connection_manager.send_to_client(client_id, ack_message)
                
            # logger.info(f"Sent stats response to client {client_id}")
            
        except Exception as e:
            # logger.error(f"Error handling request_stats: {str(e)}")
            # Send error message to client
            error_message = ErrorMessage(
                error=f"Failed to process request_stats: {str(e)}",
                details={"exception": str(e)}
            )
            await self.connection_manager.send_to_client(client_id, error_message)
    
    async def handle_worker_message(self, worker_id: str,
                                  message_type: str,
                                  message_data: Dict[str, Any], 
                                  websocket: WebSocket) -> None:
        """
        Handle a message from a worker.
        
        Args:
            worker_id: Worker identifier
            message_type: Type of message
            message_data: Message data
            websocket: WebSocket connection
        """
        # Parse message using the models
        message_obj = self.message_models.parse_message(message_data)

        logger.debug(f"[HANDLING-WORKER-MESSAGE] From worker {worker_id}: {message_obj}")
        
        if not message_obj:
            # logger.error(f"Invalid message received from worker {worker_id}")
            error_message = ErrorMessage(error="Invalid message format")
            await self.connection_manager.send_to_worker(worker_id, error_message)
            return
            
        # Process message based on type using match-case
        match message_type:
            case "register_worker":
                # Cast message to the expected type for type checking
                # Note: We use .dict() here only for creating a new typed object, not for sending
                # This ensures proper type validation while maintaining the original data
                register_message = RegisterWorkerMessage(**message_obj.dict())
                await self.handle_register_worker(worker_id, register_message)
            case "update_job_progress":
                # Cast message to the expected type for type checking
                # Create a properly typed message object
                # Note: We use .dict() here only for creating a new typed object, not for sending
                # This ensures proper type validation while maintaining the original data
                progress_message = UpdateJobProgressMessage(**message_obj.dict())
                await self.handle_update_job_progress(worker_id, progress_message)
            case "complete_job":
                # Cast message to the expected type for type checking
                # Create a properly typed message object
                # Note: We use .dict() here only for creating a new typed object, not for sending
                # This ensures proper type validation while maintaining the original data
                complete_message = CompleteJobMessage(**message_obj.dict())
                await self.handle_complete_job(worker_id, complete_message)
            case "worker_heartbeat":
                # Validate that the message has the required fields for WorkerHeartbeatMessage
                if not isinstance(message_obj, WorkerHeartbeatMessage):
                    # Create a properly typed message object with validation
                    try:
                        heartbeat_message = WorkerHeartbeatMessage(**message_obj.model_dump())
                        await self.handle_worker_heartbeat(worker_id, heartbeat_message)
                    except Exception as e:
                        error_message = ErrorMessage(error=f"Invalid WorkerHeartbeatMessage: {str(e)}")
                        await self.connection_manager.send_to_worker(worker_id, error_message)
                else:
                    await self.handle_worker_heartbeat(worker_id, message_obj)
            case "worker_status":
                # Validate that the message has the required fields for WorkerStatusMessage
                if not isinstance(message_obj, WorkerStatusMessage):
                    # Create a properly typed message object with validation
                    try:
                        status_message = WorkerStatusMessage(**message_obj.model_dump())
                        await self.handle_worker_status(worker_id, status_message)
                    except Exception as e:
                        error_message = ErrorMessage(error=f"Invalid WorkerStatusMessage: {str(e)}")
                        await self.connection_manager.send_to_worker(worker_id, error_message)
                else:
                    await self.handle_worker_status(worker_id, message_obj)
            case "claim_job":
                # Validate that the message has the required fields for ClaimJobMessage
                if not isinstance(message_obj, ClaimJobMessage):
                    # Create a properly typed message object with validation
                    try:
                        claim_message = ClaimJobMessage(**message_obj.model_dump())
                        await self.handle_claim_job(worker_id, claim_message)
                    except Exception as e:
                        error_message = ErrorMessage(error=f"Invalid ClaimJobMessage: {str(e)}")
                        await self.connection_manager.send_to_worker(worker_id, error_message)
                else:
                    await self.handle_claim_job(worker_id, message_obj)
            # The subscribe_job_notifications case has been removed
            # This functionality is now handled by the register_worker message
            case _:
                # Handle unrecognized message type
                error_message = ErrorMessage(error=f"Unsupported message type: {message_type}")
                await self.connection_manager.send_to_worker(worker_id, error_message)
            
    async def handle_register_worker(self, worker_id: str, message: RegisterWorkerMessage) -> None:
        """
        Handle worker registration - registers the worker, sets its status, and subscribes to job notifications if requested.
        
        Args:
            worker_id: Worker identifier
            message: Worker registration message
        """
        # Extract capabilities from the message
        capabilities = message.capabilities or {}
        
        # Register worker in Redis with capabilities
        self.redis_service.register_worker(worker_id, capabilities)
        logger.info(f"Worker registered: {worker_id}")
        
        # Set initial status in memory (default is idle)
        status = message.status if message.status is not None else "idle"
        self.connection_manager.worker_status[worker_id] = status
        
        # Initialize heartbeat timestamp in connection manager
        current_time = time.time()
        self.connection_manager.worker_last_heartbeat[worker_id] = current_time
        logger.debug(f"Initialized heartbeat timestamp for worker {worker_id} at {current_time:.0f}")
        
        # Subscribe to job notifications if requested
        if message.subscribe_to_jobs:
            # Add worker to job notification subscribers
            self.connection_manager.subscribe_worker_to_job_notifications(worker_id)
            
            # Send confirmation message
            confirmation = JobNotificationsSubscribedMessage(worker_id=worker_id)
            await self.connection_manager.send_to_worker(worker_id, confirmation)
            logger.info(f"Worker {worker_id} subscribed to job notifications")
        
        # Send registration confirmation
        response = WorkerRegisteredMessage(worker_id=worker_id)
        await self.connection_manager.send_to_worker(worker_id, response)
        
    async def handle_update_job_progress(self, worker_id: str, message: UpdateJobProgressMessage) -> None:
        """
        Handle job progress update from a worker.
        
        Args:
            worker_id: Worker identifier
            message: Update job progress message
        """
        # Update job progress in Redis
        self.redis_service.update_job_progress(
            job_id=message.job_id,
            progress=message.progress,
            message=message.message
        )
        
        # Forward progress update directly to the subscribed client
        # We use the same UpdateJobProgressMessage format for both worker-to-server and server-to-client communication
        # This ensures type consistency and simplifies the message flow
        await self.connection_manager.forward_job_progress(message)
        
        # logger.info(f"Job progress updated: {message.job_id}, progress: {message.progress}%")
    
    async def handle_complete_job(self, worker_id: str, message: CompleteJobMessage) -> None:
        """
        Handle job completion from a worker.
        
        Args:
            worker_id: Worker identifier
            message: Complete job message
        """
        # Update job status in Redis
        self.redis_service.complete_job(
            job_id=message.job_id,
            result=message.result
        )
        
        # Update worker status to idle in memory
        self.connection_manager.worker_status[worker_id] = "idle"
        
        # Send acknowledgment back to the worker
        # This prevents the worker from receiving its own message back
        # and ensures it knows the server has processed the completion
        ack_message = self.message_models.create_job_completed_ack_message(
            job_id=message.job_id,
            worker_id=worker_id
        )
        await self.connection_manager.send_to_worker(worker_id, ack_message)
        
        # Forward completion update to subscribed clients
        # Pass the message object directly without .dict() conversion
        # This ensures type consistency across the application
        await self.connection_manager.broadcast_job_notification(message)
        
        logger.info(f"Job completed: {message.job_id} by worker: {worker_id}")
        
        # Broadcast pending jobs to idle workers
        await self.broadcast_pending_jobs_to_idle_workers()
    
    async def handle_worker_heartbeat(self, worker_id: str, message: WorkerHeartbeatMessage) -> None:
        """
        Handle worker heartbeat.
        
        Args:
            worker_id: Worker identifier
            message: Worker heartbeat message
        """
        # Update heartbeat timestamp in connection manager (in-memory only)
        current_time = time.time()
        self.connection_manager.worker_last_heartbeat[worker_id] = current_time
        
        # Optionally update worker status if provided
        if message.status:
            # Update worker status in memory
            self.connection_manager.worker_status[worker_id] = message.status
            
            # If worker is idle, broadcast pending jobs
            if message.status == "idle":
                await self.broadcast_pending_jobs_to_idle_workers()
        
        # Log heartbeat with timestamp (debug level)
        logger.debug(f"Worker heartbeat received: {worker_id} at {current_time:.0f}")
    
    async def handle_worker_status(self, worker_id: str, message: WorkerStatusMessage) -> None:
        """
        Handle worker status update.
        
        Args:
            worker_id: Worker identifier
            message: Worker status message
        """
        # Use 'idle' as default status if message.status is None
        status = message.status if message.status is not None else "idle"
        
        # Update worker status in memory only
        self.connection_manager.worker_status[worker_id] = status
        
        # If worker is now idle, broadcast pending jobs
        if status == "idle":
            logger.info(f"Worker {worker_id} is now idle and ready for jobs")
            await self.broadcast_pending_jobs_to_idle_workers()
        
        # logger.info(f"Worker status updated: {worker_id}, status: {message.status}")
    
    async def handle_claim_job(self, worker_id: str, message: ClaimJobMessage) -> None:
        """
        Handle job claim from a worker.
        
        Args:
            worker_id: Worker identifier
            message: Claim job message
        """
        # Check if worker is idle before allowing claim (using in-memory status only)
        in_memory_status = self.connection_manager.worker_status.get(worker_id)
        logger.debug(f"Worker {worker_id} in-memory status before claim: {in_memory_status}")
        
        if in_memory_status != "idle":
            # Worker is not idle, send error message
            error_message = ErrorMessage(error=f"Cannot claim job {message.job_id}: Worker {worker_id} is not idle")
            await self.connection_manager.send_to_worker(worker_id, error_message)
            logger.warning(f"Rejected job claim: {message.job_id} by non-idle worker: {worker_id}")
            return
            
        # Attempt to claim the job in Redis
        success = self.redis_service.claim_job(message.job_id, worker_id)
        
        if success:
            # Update worker status to working in memory only
            self.connection_manager.worker_status[worker_id] = "working"
            
            # Get job details
            job_data = self.redis_service.get_job_status(message.job_id)
            
            if job_data:
                # Send job details to worker
                job_details = JobAssignedMessage(
                    job_id=message.job_id,
                    worker_id=worker_id,  # Add the required worker_id field
                    job_type=job_data.get("job_type", "unknown"),
                    priority=job_data.get("priority", 0),
                    params=job_data.get("job_request_payload", {})
                )
                await self.connection_manager.send_to_worker(worker_id, job_details)
                
                # Notify clients that job is now processing
                status_update = ResponseJobStatusMessage(
                    job_id=message.job_id,
                    status="processing",
                    worker_id=worker_id
                )
                # Pass the ResponseJobStatusMessage object directly without .dict() conversion
                # This ensures type consistency across the application
                await self.connection_manager.broadcast_job_notification(status_update)
                
                # After job is claimed, broadcast pending jobs to other idle workers
                await self.broadcast_pending_jobs_to_idle_workers()
                
                # logger.info(f"Job claimed: {message.job_id} by worker: {worker_id}")
            else:
                logger.error(f"Job claimed but details not found: {message.job_id}")
        else:
            # Job could not be claimed
            error_message = ErrorMessage(error=f"Failed to claim job {message.job_id}")
            await self.connection_manager.send_to_worker(worker_id, error_message)
            
            logger.warning(f"Failed job claim: {message.job_id} by worker: {worker_id}")
    
    async def handle_monitor_message(self, monitor_id: str,
                                   message_type: str,
                                   message_data: Dict[str, Any], 
                                   websocket: WebSocket) -> None:
        """
        Handle a message from a monitor.
        
        Args:
            monitor_id: Monitor identifier
            message_type: Type of message
            message_data: Message data
            websocket: WebSocket connection
        """
        # Process message based on type using match-case
        match message_type:
            case "subscribe":
                channels = message_data.get("channels", [])
                self.connection_manager.set_monitor_subscriptions(monitor_id, channels)
                await websocket.send_text(json.dumps({
                    "type": "subscription_confirmed",
                    "channels": channels
                }))
            case "get_system_status":
                # Send immediate system status update using the enhanced method
                await self.connection_manager.send_system_status_to_monitors(self.redis_service)
            case "stay_alive":
                # Respond to stay_alive to keep connection alive
                await websocket.send_text(json.dumps({
                    "type": "stay_alive_response",
                    "timestamp": time.time()
                }))
            case _:
                # Handle unrecognized message type
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "error": f"Unsupported message type: {message_type}"
                }))
   
    # Background task methods
    async def _broadcast_stats_task(self) -> None:
        """
        Periodically fetch stats from Redis and broadcast to monitors
        
        This task fetches detailed system statistics including information about
        active jobs and workers, and broadcasts them to all connected monitors.
        Regular clients do not receive these broadcasts as they only need
        information about their specific jobs.
        """
        last_stats = None  # Track previous stats to detect changes
        
        while True:
            try:
                # Check if there are any monitors connected
                monitor_connections = self.connection_manager.monitor_connections
                monitors_count = len(monitor_connections) if hasattr(monitor_connections, '__len__') else 0
                
                # Skip if no monitors are connected
                if monitors_count == 0:
                    await asyncio.sleep(3)  # Check less frequently if no monitors
                    continue
                    
                # Get detailed stats from Redis
                current_stats = self.redis_service.request_stats()
                
                # Skip broadcast if stats haven't changed
                if current_stats == last_stats:
                    await asyncio.sleep(1)  # Check frequently but don't broadcast
                    continue
                    
                # Update last_stats for next comparison
                last_stats = current_stats
                
                # Serialize the stats to ensure JSON compatibility
                serializable_stats = self._serialize_stats(current_stats)
                
                # Create a proper StatsBroadcastMessage using the factory method
                # Build the connections dictionary
                connections = {
                    "clients": list(self.connection_manager.client_connections.keys()),
                    "workers": list(self.connection_manager.worker_connections.keys()),
                    "monitors": list(self.connection_manager.monitor_connections.keys())
                }
                
                # Build the subscriptions dictionary
                subscriptions = {
                    "stats": list(self.connection_manager.stats_subscriptions),
                    "job_notifications": list(self.connection_manager.job_notification_subscriptions),
                    "jobs": self.connection_manager.job_subscriptions
                }
                
                # Build the workers dictionary
                workers = {}
                for worker_id, status in self.connection_manager.worker_status.items():
                    # Check if the worker is subscribed to job notifications AND not disconnected
                    is_accepting_jobs = (worker_id in self.connection_manager.job_notification_subscriptions and 
                                       status != "disconnected" and 
                                       worker_id in self.connection_manager.worker_connections)
                    workers[worker_id] = {
                        "status": status, 
                        "connection_status": status,
                        "is_accepting_jobs": is_accepting_jobs  # Add field to show if worker is accepting jobs
                    }
                
                # Create the stats broadcast message
                stats_broadcast = self.message_models.create_stats_broadcast_message(
                    connections=connections,
                    workers=workers,
                    subscriptions=subscriptions,
                    system=serializable_stats
                )
                
                # Broadcast to monitors only - the broadcast_stats method now only sends to monitors
                await self.connection_manager.broadcast_to_monitors(stats_broadcast)
                
            except Exception as e:
                logger.error(f"Error in stats broadcast task: {str(e)}")
                
            # Sleep before next update
            await asyncio.sleep(1)
    
    async def broadcast_pending_jobs_to_idle_workers(self) -> bool:
        """
        Broadcast pending jobs to idle workers based on in-memory worker status.
        
        This method:
        1. Checks for idle workers in the connection manager's in-memory state
        2. Gets the next highest priority pending job from Redis
        3. Broadcasts job notifications to idle workers
        
        Returns:
            bool: True if a job was broadcast, False otherwise
        """
        try:
            # Log the current worker status dictionary
            logger.info(f"[DEBUG] Current worker status: {self.connection_manager.worker_status}")
            
            # Get idle workers from in-memory state
            idle_workers = []
            for worker_id, status in self.connection_manager.worker_status.items():
                if status == "idle":
                    idle_workers.append(worker_id)
                logger.info(f"[DEBUG] Worker {worker_id} status: {status}")
            
            if not idle_workers:
                logger.info("[DEBUG] No idle workers available for job assignment")
                return False
            else:
                logger.info(f"[DEBUG] Found {len(idle_workers)} idle workers: {idle_workers}")
                
            # Get the next pending job from Redis
            logger.info("[DEBUG] Attempting to get next pending job from Redis")
            next_job = self.redis_service.get_next_pending_job()
            
            if not next_job:
                logger.info("[DEBUG] No pending jobs available for assignment")
                return False
            else:
                logger.info(f"[DEBUG] Found pending job: {next_job}")
                
            job_id = next_job.get("id")
            # Ensure job_id is a string to satisfy type requirements
            if job_id is None or not isinstance(job_id, str):
                # Generate a default job_id if none exists or it's not a string
                job_id = str(uuid.uuid4())
                logger.warning(f"[DEBUG] Missing or invalid job_id in next_job, generated default: {job_id}")
                
            job_type = next_job.get("job_type", "unknown")
            priority = int(next_job.get("priority", 0))
            job_request_payload = next_job.get("job_request_payload", {})
            
            logger.info(f"[DEBUG] Job details - ID: {job_id}, Type: {job_type}, Priority: {priority}")
            logger.info(f"[DEBUG] Job payload type: {type(job_request_payload)}")
            
            # Parse job_request_payload if it's a string (JSON)
            if isinstance(job_request_payload, str):
                try:
                    import json
                    job_request_payload = json.loads(job_request_payload)
                    logger.info(f"[DEBUG] Successfully parsed job_request_payload from string to dict: {job_request_payload}")
                except json.JSONDecodeError as e:
                    logger.error(f"[DEBUG] Error parsing job_request_payload as JSON: {str(e)}")
                    job_request_payload = {}  # Use empty dict as fallback
            
            # Create job available notification using the proper message class
            # This ensures proper validation and type handling
            try:
                notification = JobAvailableMessage(
                    job_id=job_id,
                    job_type=job_type,
                    priority=priority,
                    job_request_payload=job_request_payload
                )
                logger.info(f"[DEBUG] Created JobAvailableMessage successfully")
            except Exception as msg_error:
                logger.error(f"[DEBUG] Error creating JobAvailableMessage: {str(msg_error)}")
                return False
            
            # Send notification to idle workers
            logger.info(f"[DEBUG] Broadcasting job {job_id} to {len(idle_workers)} idle workers")
            try:
                result = await self.connection_manager.notify_idle_workers(notification)
                logger.info(f"[DEBUG] notify_idle_workers result: {result}")
                return True
            except Exception as notify_error:
                logger.error(f"[DEBUG] Error in notify_idle_workers: {str(notify_error)}")
                return False
            
        except Exception as e:
            logger.error(f"[DEBUG] Error broadcasting pending jobs: {str(e)}")
            return False
    
    async def _cleanup_stale_claims_task(self) -> None:
        """
        Periodically check for and clean up stale job claims
        """
        while True:
            try:
                # Perform cleanup
                cleaned_jobs = self.redis_service.cleanup_stale_claims()
                
                # Ensure cleaned_jobs is a dict before using len() and items()
                if cleaned_jobs and isinstance(cleaned_jobs, dict) and len(cleaned_jobs) > 0:
                    # logger.info(f"Cleaned up {len(cleaned_jobs)} stale job claims")
                    
                    # For each cleaned job, notify idle workers about it
                    for job_id, job_data in cleaned_jobs.items():
                        # Create job available notification
                        notification = {
                            "type": "job_available",
                            "job_id": job_id,
                            "job_type": job_data.get("job_type", "unknown"),
                            "priority": int(job_data.get("priority", 0)),
                            "job_request_payload": job_data.get("job_request_payload", {})
                        }
                        
                        # Send notification to idle workers
                        await self.connection_manager.notify_idle_workers(notification)
                    
                    # After cleaning up stale claims, broadcast any pending jobs
                    await self.broadcast_pending_jobs_to_idle_workers()
                        
            except Exception as e:
                logger.error(f"Error in stale claims cleanup task: {str(e)}")
                
            # Sleep before next cleanup
            await asyncio.sleep(30)  # Check every 30 seconds
    
    async def _mark_stale_workers_task(self) -> None:
        """
        Periodically check for and mark stale workers as disconnected
        """
        while True:
            try:
                # Get stale workers and mark them as disconnected
                # Use the mark_stale_workers method which handles both identifying stale workers
                # and updating their status in a single operation
                stale_workers = self.redis_service.mark_stale_workers()
                
                if stale_workers and len(stale_workers) > 0:
                    # logger.info(f"Marked {len(stale_workers)} workers as disconnected due to inactivity")
                    
                    # Update connection manager with disconnected workers
                    for worker_id in stale_workers:
                        await self.connection_manager.disconnect_worker(worker_id)
                        
            except Exception as e:
                logger.error(f"Error in stale workers cleanup task: {str(e)}")
                
            # Sleep before next cleanup
            await asyncio.sleep(60)  # Check every minute
    
    async def _monitor_status_update_task(self) -> None:
        """
        Periodically send system status updates to connected monitors
        """
        while True:
            try:
                # Check if there are any monitors connected
                monitors_count = len(self.connection_manager.monitor_connections)
                
                # Skip if no monitors are connected
                if monitors_count == 0:
                    await asyncio.sleep(5)  # Check less frequently if no monitors
                    continue
                    
                # Send system status to all connected monitors
                await self.connection_manager.send_system_status_to_monitors(self.redis_service)
                
            except Exception as e:
                logger.error(f"Error in monitor status update task: {str(e)}")
                
            # Sleep before next update
            await asyncio.sleep(5)  # Update every 5 seconds
    
    async def _start_redis_listener(self) -> None:
        """
        Start listening for Redis pub/sub messages
        """
        # logger.info("Starting Redis pub/sub listener")
        
        # Connect to Redis async client
        try:
            await self.redis_service.connect_async()
            # logger.info("Successfully connected to Redis async client")
        except Exception as e:
            logger.error(f"Failed to connect to Redis async client: {str(e)}")
            return
            
        # Define job update message handler
        async def handle_job_update(message):
            try:
                # Parse message data
                data = json.loads(message["data"])
                job_id = data.get("job_id")
                
                if job_id:
                    # Check for subscribed client
                    await self.connection_manager.send_job_update(job_id, data)
            except Exception as e:
                logger.error(f"Error handling Redis job update message: {str(e)}")
        
        # Define job notification message handler
        async def handle_job_notification(message):
            try:
                # Parse message data
                data = json.loads(message["data"])
                message_type = data.get("type")
                
                if message_type == "job_available":
                    job_id = data.get("job_id")
                    job_type = data.get("job_type")
                    
                    if job_id and job_type:
                        # Create job available notification message
                        notification = {
                            "type": "job_available",
                            "job_id": job_id,
                            "job_type": job_type,
                            "job_request_payload": data.get("job_request_payload")
                        }
                        
                        # Send notification to idle workers
                        worker_count = await self.connection_manager.notify_idle_workers(notification)
                        # logger.info(f"Notified {worker_count} idle workers about job {job_id}")
                
            except Exception as e:
                logger.error(f"Error handling Redis job notification message: {str(e)}")
        
        # Subscribe to channels
        try:
            await self.redis_service.subscribe_to_channel("job_updates", handle_job_update)
            await self.redis_service.subscribe_to_channel("job_notifications", handle_job_notification)
        except Exception as e:
            logger.error(f"Error subscribing to Redis channels: {str(e)}")
    
    async def handle_subscribe_job(self, client_id: str, job_id: str) -> None:
        """
        Handle job subscription request from a client.
        
        Args:
            client_id: Client identifier
            job_id: Job identifier
        """
        await self.connection_manager.subscribe_to_job(job_id, client_id)
    
    # The handle_subscribe_job_notifications method has been removed
    # Its functionality is now part of handle_register_worker
    # This ensures a cleaner, more consolidated registration process
