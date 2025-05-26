#!/usr/bin/env python3
# Implementation of the MessageHandlerInterface
import asyncio
import json
import time
import uuid
from typing import Dict, Any, Optional, Callable, Awaitable, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosedError
from pydantic import ValidationError  # Add this import

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
    ResponseJobStatusMessage, WorkerCapabilities,
    FailJobMessage
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
        
        # Set ConnectionManager reference in RedisService
        self.redis_service.set_connection_manager(connection_manager)

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
        self._background_tasks.append(asyncio.create_task(self._monitor_status_update_task()))
        self._background_tasks.append(asyncio.create_task(self._start_redis_listener()))

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
            case "cancel_job":
                job_id = message_data.get("job_id")
                reason = message_data.get("reason", "Manually cancelled")
                if job_id:
                    await self.handle_cancel_job(client_id, job_id, reason)
                else:
                    error_message = ErrorMessage(error="Missing job_id in cancel_job request")
                    await self.connection_manager.send_to_client(client_id, error_message)
            # [2025-05-19T18:26:00-04:00] Added force_retry_job case
            case "force_retry_job":
                job_id = message_data.get("job_id")
                if job_id:
                    await self.handle_force_retry_job(client_id, job_id)
                else:
                    error_message = ErrorMessage(error="Missing job_id in force_retry_job request")
                    await self.connection_manager.send_to_client(client_id, error_message)
            case "stay_alive":
                # Respond with a simple acknowledgment
                # WebSocket protocol handles connection keepalive automatically
                # Using ResponseJobStatusMessage for the acknowledgment
                response = ResponseJobStatusMessage(
                    job_id="keep-alive",  # Using a special ID for keep-alive messages
                    status="acknowledged",
                    message="Connection is alive"
                )
                await self.connection_manager.send_to_client(client_id, response)
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
        # Check if message_id is present in the request, use it as job_id if it exists
        # Otherwise generate a new UUID
        if 'message_id' in message and message['message_id']:
            job_id = message['message_id']
        else:
            job_id = f"job-{uuid.uuid4()}"

        # Extract data directly from the message dictionary
        # Using .get() with default values to handle missing keys
        job_type = message.get('job_type', 'unknown')
        priority = message.get('priority', 0)
        payload = message.get('payload', {})

        # Add detailed comment explaining type handling
        # We're using dictionary access instead of attribute access because
        # the method signature expects Dict[str, Any] rather than SubmitJobMessage

        # Debug logging
        #logger.debug(f"[message_handler.py handle_submit_job() ] Job Data Values: Job ID: {job_id}, Job Type: {job_type}, Priority: {priority}, Payload: {payload}, Client ID: {client_id}")
        # Add job to Redis
        job_data = self.redis_service.add_job(
            job_id=job_id,
            job_type=job_type,
            priority=priority,
            job_request_payload=payload,
            client_id=client_id
        )

        # Debug logging for job addition
        logger.debug(f"[message_handler.py  handle_submit_job() {job_id}] Job added to Redis")

        # Send confirmation response
        # Note: We're not directly notifying workers here anymore
        # Worker notification will happen through broadcast_pending_jobs_to_idle_workers

        job_queue = self.redis_service.get_jobs_by_status_type_priority(status='pending', job_type=job_type)


        # Debug logging for job queue
        # logger.debug(f"[message_handler.py  handle_submit_job()] Job queue: {job_queue}")


        job = next((job for job in job_queue if job['job_id'] == job_id), None)

        if job is None:
            logger.error(f"[message_handler.py  handle_submit_job() {job_id}] Job not found in queue")
            position = -1
            return
        else:
            position = job.get('position', -1)

        logger.debug(f"[message_handler.py  handle_submit_job() {job_id}] Job position is: {position}")

        response = JobAcceptedMessage(
            job_id=job_id,
            position=position,
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

        # logger.debug(f"[HANDLING-WORKER-MESSAGE] From worker {worker_id}: {message_obj}")


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
            case "fail_job":
                # Cast message to the expected type for type checking
                # Create a properly typed message object for job failure
                # Note: We use .dict() here only for creating a new typed object, not for sending
                # This ensures proper type validation while maintaining the original data
                try:
                    fail_message = FailJobMessage(**message_obj.dict())
                    await self.handle_fail_job(worker_id, fail_message)
                except Exception as e:
                    error_message = ErrorMessage(error=f"Invalid FailJobMessage: {str(e)}")
                    await self.connection_manager.send_to_worker(worker_id, error_message)
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
            case "connector_ws_status":
                # Forward connector WebSocket status to monitors
                # This is strictly for monitoring purposes
                from core.message_models import ConnectorWebSocketStatusMessage
                
                try:
                    # Ensure we have a properly typed message object
                    if not isinstance(message_obj, ConnectorWebSocketStatusMessage):
                        ws_status_message = ConnectorWebSocketStatusMessage(**message_obj.model_dump())
                    else:
                        ws_status_message = message_obj
                        
                    # Forward the status message to monitors
                    await self.connection_manager.forward_connector_ws_status(ws_status_message)
                    
                except Exception as e:
                    # Send error back to worker
                    error_message = ErrorMessage(error=f"Error processing ConnectorWebSocketStatusMessage: {str(e)}")
                    await self.connection_manager.send_to_worker(worker_id, error_message)
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
        # Register worker in ConnectionManager (in-memory)
        success = self.connection_manager.register_worker(worker_id, message.capabilities)
        
        if success:
            # Send registration confirmation
            response = WorkerRegisteredMessage(
                worker_id=worker_id,
                status="active"
            )
            await self.connection_manager.send_to_worker(worker_id, response)
            
            # Subscribe to job notifications if requested
            if message.subscribe_to_jobs:
                self.connection_manager.subscribe_worker_to_job_notifications(worker_id)
                
                # Send subscription confirmation
                subscription_response = JobNotificationsSubscribedMessage(worker_id=worker_id)
                await self.connection_manager.send_to_worker(worker_id, subscription_response)
            
            # Broadcast pending jobs to the newly registered worker if it's idle
            if message.status == "idle":
                await self.broadcast_pending_jobs_to_idle_workers()
        else:
            # Send error if registration failed
            error_message = ErrorMessage(error=f"Failed to register worker {worker_id}")
            await self.connection_manager.send_to_worker(worker_id, error_message)

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

    async def handle_complete_job(self, worker_id: str, message: CompleteJobMessage) -> None:
        """
        Handle job completion from a worker.

        Args:
            worker_id: Worker identifier
            message: Complete job message
        """
        # [2025-05-20T18:23:00-04:00] Log the message contents to help with debugging
        job_id = message.job_id
        result = message.result
        
        # Log the result data if available
        if result:
            if isinstance(result, dict):
                result_keys = list(result.keys())                
                # Check for base64 image data
                base64_found = False
                
                # Look for images in different possible locations
                if "images" in result:
                    image_count = len(result["images"]) if isinstance(result["images"], list) else "not a list"
                    base64_found = True
                elif "output" in result and isinstance(result["output"], dict) and "images" in result["output"]:
                    image_count = len(result["output"]["images"]) if isinstance(result["output"]["images"], list) else "not a list"
                    base64_found = True
                
                # Look for base64 data directly
                if not base64_found:
                    for key, value in result.items():
                        if isinstance(value, str) and len(value) > 100 and ",base64," in value:
                            base64_found = True
                            break
        
        # [2025-05-20T18:46:00-04:00] Update job status in Redis with the full result data
        # This ensures the result is available when the complete_job message is generated        

        # [2025-05-20T21:34:00-04:00] Store the result in Redis and ensure it completes
        # Use asyncio.to_thread to run the synchronous complete_job method in a separate thread
        # This allows us to await its completion without changing the method itself
        try:
            storage_success = await asyncio.to_thread(
                self.redis_service.complete_job,
                job_id=job_id,
                result=result  # Pass the full result data from the worker
            )
        except Exception as e:
            logger.error(f"[2025-05-20T21:34:00-04:00] Error running complete_job in thread: {str(e)}")
            storage_success = False
        
        # [2025-05-20T23:25:00-04:00] Send the complete_job message directly after storing the result
        # Since we've removed the Redis publication, we need to send this message directly
        if storage_success:
            try:
                # [2025-05-20T23:51:00-04:00] Create a proper CompleteJobMessage object
                # This ensures type compatibility with the send_to_client method
                complete_message = CompleteJobMessage(
                    job_id=job_id,
                    worker_id=worker_id,  # We have the worker_id from the function parameters
                    result=result
                )
                
                # Send the complete job message to all clients subscribed to this job
                # [2025-05-25T15:00:00-04:00] Convert CompleteJobMessage to dict for forward_job_completion
                if hasattr(complete_message, 'model_dump'):
                    message_dict = complete_message.model_dump()
                elif hasattr(complete_message, 'dict'):
                    message_dict = complete_message.dict()
                else:
                    message_dict = {
                        "job_id": job_id,
                        "type": "complete_job",
                        "worker_id": getattr(complete_message, 'worker_id', ""),
                        "result": getattr(complete_message, 'result', None)
                    }
                await self.connection_manager.forward_job_completion(job_id, message_dict)
            except Exception as e:
                logger.error(f"[2025-05-20T23:25:00-04:00] Error sending complete_job message: {str(e)}")
        else:
            logger.error(f"[2025-05-20T23:25:00-04:00] Not sending complete_job message due to storage failure for job {job_id}")
            
        
        # [2025-05-20T19:15:00-04:00] Verify the data was stored correctly by immediately querying Redis
        job_data = self.redis_service.get_job_status(job_id)
        
        # Log the retrieved data for comparison
        if job_data and "result" in job_data:
            # Log the raw result data without trying to parse it
            stored_result = job_data["result"]
            
            # Log the size of the stored result
            stored_size = len(stored_result) if isinstance(stored_result, (str, bytes)) else "unknown"
            
            # [2025-05-20T23:52:00-04:00] Log a preview of the raw result with proper type handling
            if isinstance(stored_result, bytes):
                # Handle bytes by decoding or using a safe representation
                try:
                    # Try to decode as UTF-8 first
                    if len(stored_result) > 200:
                        preview = stored_result[:200].decode('utf-8', errors='replace') + "..."
                    else:
                        preview = stored_result.decode('utf-8', errors='replace')
                except Exception:
                    # Fallback to a safe representation
                    preview = f"<binary data, {len(stored_result)} bytes>"
            elif isinstance(stored_result, str):
                # Handle strings
                if len(stored_result) > 200:
                    preview = stored_result[:200] + "..."
                else:
                    preview = stored_result
            else:
                # Handle other types
                preview = repr(stored_result)
                            
            # [2025-05-20T19:15:00-04:00] Process the stored result based on its type
            processed_result = None
            try:
                if isinstance(stored_result, dict):
                    # If it's already a dictionary, use it directly
                    processed_result = stored_result
                elif isinstance(stored_result, bytes):
                    # If it's bytes, decode to string first
                    decoded = stored_result.decode('utf-8')
                    # Then parse the string as JSON
                    processed_result = json.loads(decoded)
                elif isinstance(stored_result, str):
                    # If it's a string, parse it as JSON
                    processed_result = json.loads(stored_result)
                else:
                    logger.warning(f"[REDIS-VERIFY] Unexpected result type: {type(stored_result).__name__}")
                    processed_result = stored_result
                
            except Exception as e:
                logger.error(f"[REDIS-VERIFY] Error processing result: {str(e)}")
                logger.error(f"[REDIS-VERIFY] Failed to process result for job {job_id}")
        else:
            logger.error(f"[REDIS-VERIFY] Failed to retrieve result from Redis for job {job_id}")
            logger.error(f"[REDIS-VERIFY] Job data: {job_data}")
        

        # Update worker status to idle and clear job assignment
        # This also updates worker_info with the new status
        self.connection_manager.update_worker_job_assignment(worker_id, "idle")
        
        # Update job statistics in worker_info if available
        if worker_id in self.connection_manager.worker_info:
            # Increment jobs processed count
            if "jobs_processed" in self.connection_manager.worker_info[worker_id]:
                self.connection_manager.worker_info[worker_id]["jobs_processed"] += 1
            
            # Update last job completed timestamp
            self.connection_manager.worker_info[worker_id]["last_job_completed_at"] = time.time()

        # Send acknowledgment back to the worker
        # This prevents the worker from receiving its own message back
        # and ensures it knows the server has processed the completion
        ack_message = self.message_models.create_job_completed_ack_message(
            job_id=job_id,
            worker_id=worker_id
        )
        await self.connection_manager.send_to_worker(worker_id, ack_message)

    async def handle_cancel_job(self, client_id: str, job_id: str, reason: str = "Manually cancelled") -> None:
        """
        Handle job cancellation request from a client.
        
        This method permanently cancels a job and removes it from the queue.

        Args:
            client_id: Client identifier
            job_id: ID of the job to cancel
            reason: Reason for cancellation
        """
        # 2025-04-26-21:30 - Added method to handle job cancellation requests
        
        # Log the cancellation request
        logger.debug(f"[message_handler.py handle_cancel_job()]: Client {client_id} requested cancellation of job {job_id} with reason: {reason}")
        
        # Cancel the job in Redis
        success = self.redis_service.cancel_job(job_id, reason)
        
        if success:
            # Create a response message
            response = ResponseJobStatusMessage(
                job_id=job_id,
                status="cancelled",
                message=f"Job cancelled: {reason}"
            )
            
            # Send response to the client
            await self.connection_manager.send_to_client(client_id, response)
            
            # Also notify any subscribers to this job
            await self.connection_manager.send_job_update(job_id, response)
            
            logger.debug(f"[message_handler.py handle_cancel_job()]: Successfully cancelled job {job_id}")
        else:
            # Create an error message
            error_message = ErrorMessage(error=f"Failed to cancel job {job_id}. Job may not exist or is already in a terminal state.")
            
            # Send error to the client
            await self.connection_manager.send_to_client(client_id, error_message)
            
            logger.error(f"[message_handler.py handle_cancel_job()]: Failed to cancel job {job_id}")
    
    # [2025-05-19T18:27:00-04:00] Added method to handle force retry job requests
    async def handle_force_retry_job(self, client_id: str, job_id: str) -> None:
        """
        Handle force retry job request from a client.
        
        This method clears a job's failure history, allowing it to be assigned to any worker,
        even ones that previously failed it.
        
        Args:
            client_id: Client identifier
            job_id: ID of the job to force retry
        """
        # Log the force retry request
        logger.debug(f"[message_handler.py handle_force_retry_job()]: Client {client_id} requested force retry of job {job_id}")
        
        # Get the job status from Redis to verify it exists
        job_data = self.redis_service.get_job_status(job_id)
        
        if not job_data:
            # Job doesn't exist
            error_message = ErrorMessage(error=f"Failed to force retry job {job_id}. Job does not exist.")
            await self.connection_manager.send_to_client(client_id, error_message)
            logger.error(f"[message_handler.py handle_force_retry_job()]: Failed to force retry job {job_id} - job not found")
            return
        
        # Clear the job's failure history using the connection manager's force_retry_job method
        success = self.connection_manager.force_retry_job(job_id)
        
        if success:
            # Create a response message
            response = ResponseJobStatusMessage(
                job_id=job_id,
                status=job_data.get("status", "unknown"),
                message=f"Job failure history cleared. Job can now be assigned to any worker."
            )
            
            # Send response to the client
            await self.connection_manager.send_to_client(client_id, response)
            
            # Also notify any subscribers to this job
            await self.connection_manager.send_job_update(job_id, response)
            
            # If the job is pending, trigger a job notification to workers
            if job_data.get("status") == "pending":
                # Get the job details
                # [2025-05-25T15:00:00-04:00] Ensure job_type is a string as required by JobAvailableMessage
                job_type = job_data.get("type", "")
                if job_type is None:
                    job_type = ""
                priority = int(job_data.get("priority", 0))
                
                # Create a job notification message
                job_notification = JobAvailableMessage(
                    job_id=job_id,
                    job_type=job_type,
                    priority=priority
                )
                
                # Notify idle workers about the job
                await self.connection_manager.notify_idle_workers(job_notification)
            
        else:
            # No workers had failed this job
            response = ResponseJobStatusMessage(
                job_id=job_id,
                status=job_data.get("status", "unknown"),
                message=f"Job has no failure history to clear."
            )
            
            # Send response to the client
            await self.connection_manager.send_to_client(client_id, response)
                
    async def handle_fail_job(self, worker_id: str, message: FailJobMessage) -> None:
        """
        Handle job failure message from a worker.
        
        This method marks the job as failed in Redis and requeues it for processing.

        Args:
            worker_id: Worker identifier
            message: Job failure message
        """
        # 2025-04-17-15:44 - Restored handle_fail_job method to process fail_job messages
        job_id = message.job_id
        # Ensure error is a string, not None
        error = message.error if hasattr(message, 'error') and message.error is not None else "Unknown error"

        # Log the failure
        logger.error(f"[message_handler.py handle_fail_job()]: Job {job_id} failed on worker {worker_id} with error: {error}")

        # 2025-04-25-23:25 - Record the failed job in the ConnectionManager
        # This updates the in-memory tracking to prevent this worker from being notified about this job again
        self.connection_manager.record_failed_job(worker_id, job_id)
        
        # Mark the job as failed in Redis
        success = self.redis_service.fail_job(job_id, error)

        if success:
            # Send acknowledgment to worker using the new JobFailedAckMessage
            # 2025-04-17-16:00 - Updated to use JobFailedAckMessage instead of generic AckMessage
            ack_message = self.message_models.create_job_failed_ack_message(
                job_id=job_id,
                worker_id=worker_id,
                error=error
            )
            await self.connection_manager.send_to_worker(worker_id, ack_message)
            
            # Update worker status to idle and clear job assignment
            # This also updates worker_info with the new status
            self.connection_manager.update_worker_job_assignment(worker_id, "idle")
            
            # The fail_job method in redis_service already handles the requeuing logic
            # by marking the job as failed and publishing a job update
            
            logger.debug(f"[message_handler.py handle_fail_job()]: Job {job_id} marked as failed and requeued")
            
            # Broadcast pending jobs to idle workers
            await self.broadcast_pending_jobs_to_idle_workers()
        else:
            # Send error to worker
            error_message = ErrorMessage(error=f"Failed to mark job {job_id} as failed")
            await self.connection_manager.send_to_worker(worker_id, error_message)
            
            logger.warning(f"[message_handler.py handle_fail_job()]: Failed to mark job {job_id} as failed by worker {worker_id}")

        # Forward completion update to subscribed clients
        # Pass the message object directly without .dict() conversion
        # This ensures type consistency across the application
        await self.connection_manager.broadcast_job_notification(message)

        # Broadcast pending jobs to idle workers
        await self.broadcast_pending_jobs_to_idle_workers()

    async def handle_worker_heartbeat(self, worker_id: str, message: WorkerHeartbeatMessage) -> None:
        """
        Handle worker heartbeat.

        Args:
            worker_id: Worker identifier
            message: Worker heartbeat message
        """
        # Update heartbeat timestamp in connection manager
        current_time = time.time()
        self.connection_manager.worker_last_heartbeat[worker_id] = current_time
        
        # Optionally update worker status if provided
        if message.status:
            # Update worker status using ConnectionManager's method
            await self.connection_manager.update_worker_status(worker_id, message.status)
            
            # If worker is idle, broadcast pending jobs
            if message.status == "idle":
                await self.broadcast_pending_jobs_to_idle_workers()
        
        # Send heartbeat acknowledgment back to worker
        try:
            # Create heartbeat acknowledgment message using the proper model
            from .message_models import WorkerHeartbeatAckMessage
            
            heartbeat_ack = WorkerHeartbeatAckMessage(
                worker_id=worker_id,
                timestamp=current_time
            )
            # Send it back to the worker
            await self.connection_manager.send_to_worker(worker_id, heartbeat_ack)
            #logger.debug(f"[message_handler.py handle_worker_heartbeat()]: Sent heartbeat acknowledgment to worker {worker_id}")
        except Exception as e:
            logger.error(f"[message_handler.py handle_worker_heartbeat()]: Error sending heartbeat acknowledgment to worker {worker_id}: {str(e)}")

    async def handle_worker_status(self, worker_id: str, message: WorkerStatusMessage) -> None:
        """
        Handle worker status update.

        Args:
            worker_id: Worker identifier
            message: Worker status message
        """
        # Use 'idle' as default status if message.status is None
        status = message.status if message.status is not None else "idle"
        
        # Update worker status in memory and job assignment tracking
        # This handles the comprehensive worker state management
        self.connection_manager.update_worker_job_assignment(worker_id, status)
        
        # Also use the async method to broadcast status to monitors
        await self.connection_manager.update_worker_status(worker_id, status)
        
        # If worker is now idle, broadcast pending jobs
        if status == "idle":
            await self.broadcast_pending_jobs_to_idle_workers()

    async def handle_claim_job(self, worker_id: str, message: ClaimJobMessage) -> None:
        """
        Handle job claim from a worker.

        Args:
            worker_id: Worker identifier
            message: Claim job message
        """
        # Check if worker is idle before allowing claim (using in-memory status only)
        in_memory_status = self.connection_manager.worker_status.get(worker_id)
        #logger.debug(f"Worker {worker_id} in-memory status before claim: {in_memory_status}")

        if in_memory_status != "idle":
            # Worker is not idle, send error message
            error_message = ErrorMessage(error=f"Cannot claim job {message.job_id}: Worker {worker_id} is not idle")
            await self.connection_manager.send_to_worker(worker_id, error_message)
            #logger.warning(f"Rejected job claim: {message.job_id} by non-idle worker: {worker_id}")
            return

        # Attempt to claim the job in Redis
        success = self.redis_service.claim_job(message.job_id, worker_id)

        if success:
            # Update worker status and job assignment using the comprehensive method
            self.connection_manager.update_worker_job_assignment(worker_id, "working", message.job_id)

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

            else:
                logger.error(f"Job claimed but details not found: {message.job_id}")
        else:
            # Job could not be claimed
            error_message = ErrorMessage(error=f"Failed to claim job {message.job_id}")
            await self.connection_manager.send_to_worker(worker_id, error_message)

            logger.error(f"Failed job claim: {message.job_id} by worker: {worker_id}")

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
        Broadcast pending jobs to idle workers based on capabilities and job types.

        This method implements an intelligent job-worker matching algorithm:
        1. Identifies idle workers and their capabilities
        2. Gets available jobs grouped by job type
        3. Matches jobs to workers based on capabilities
        4. Ensures each worker only receives one job notification per cycle
        5. Prioritizes jobs based on priority and age

        Returns:
            bool: True if at least one job was broadcast, False otherwise
        """
        try:
            # Track if any jobs were broadcast
            jobs_broadcast = False

            # Step 1: Get idle workers and their capabilities
            idle_workers = []
            worker_job_types = {}

            for worker_id, status in self.connection_manager.worker_status.items():
                if status == "idle":
                    idle_workers.append(worker_id)

                    # logger.debug(f"[TEST-LOG] Worker {worker_id} capabilities: {self.connection_manager.worker_capabilities.get(worker_id, {})}")
                    # Get worker capabilities from in-memory storage
                    try:
                    # Get raw capabilities from memory
                        raw_capabilities = self.connection_manager.worker_capabilities.get(worker_id, {})

                        # Parse capabilities using WorkerCapabilities model
                        capabilities = WorkerCapabilities(**raw_capabilities)

                        capabilities_dict = capabilities.dict()

                        # Get supported job types
                        supported_job_types = capabilities_dict.get("supported_job_types", [])
                    except ValidationError as e:
                        logger.error(f"[message_handler.py broadcast_pending_jobs_to_idle_workers] Error parsing capabilities for worker {worker_id}: {str(e)}")
                        # Fallback to a minimal capabilities object
                        capabilities = WorkerCapabilities()
                        supported_job_types = []
                    except Exception as e:
                        logger.error(f"[message_handler.py broadcast_pending_jobs_to_idle_workers] Generic Error: {str(e)}")
                        # Fallback to a minimal capabilities object
                        capabilities = WorkerCapabilities()
                        supported_job_types = []

                    # Ensure supported_job_types is always a list
                    if not isinstance(supported_job_types, list):
                        if supported_job_types:
                            supported_job_types = [supported_job_types]
                        else:
                            supported_job_types = []

                    # Store supported job types for this worker
                    # This is a polling situation where we are checking all the workers capabilities over and over. (this is a loop, foreach worker record their capabilities)
                    worker_job_types[worker_id] = supported_job_types

            if not idle_workers:
                return False

            # Step 2: Collect all unique job types supported by idle workers
            all_supported_job_types = set()
            for job_types in worker_job_types.values():
                all_supported_job_types.update(job_types)

            if not all_supported_job_types:
                return False


            # Step 3: Get pending jobs for each supported job type
            available_jobs = {}
            for job_type in all_supported_job_types:
                # Get pending jobs of this type
                jobs = self.redis_service.get_pending_jobs_by_type(job_type)
                if jobs:
                    available_jobs[job_type] = jobs

            if not available_jobs:
                return False

            # Step 4: Match jobs to workers based on capabilities
            # Track which workers have been notified in this cycle
            notified_workers = set()

            # Process jobs in priority order across all job types
            all_jobs = []
            for job_type, jobs in available_jobs.items():
                for job in jobs:
                    # Add job type to the job dict for reference
                    job["job_type"] = job_type
                    all_jobs.append(job)

            # Sort jobs by priority (highest first) and then by creation time (oldest first)
            all_jobs.sort(key=lambda j: (-int(j.get("priority", 0)), float(j.get("created_at", 0))))

            for job in all_jobs:
                job_id = job.get("id")
                job_type = job.get("job_type")
                priority = int(job.get("priority", 0))

                if not job_id or not isinstance(job_id, str):
                    job_id = str(uuid.uuid4())
                    #logger.warning(f"[JOB-MATCH] Missing or invalid job_id, generated default: {job_id}")

                # Find eligible workers for this job type
                eligible_workers = []
                excluded_workers = []
                
                for worker_id in idle_workers:
                    # Skip workers that have already been notified in this cycle
                    if worker_id in notified_workers:
                        continue
                        
                    # Skip workers that don't support this job type
                    if job_type not in worker_job_types.get(worker_id, []):
                        continue
                        
                    # 2025-04-25-23:30 - Check if worker has previously failed this job
                    # This is the new in-memory approach to prevent reassigning failed jobs
                    if worker_id in self.connection_manager.worker_failed_jobs and job_id in self.connection_manager.worker_failed_jobs[worker_id]:
                        excluded_workers.append(worker_id)
                        continue
                        
                    # Worker is eligible
                    eligible_workers.append(worker_id)

                if not eligible_workers:
                    continue

                # Get the job request payload
                job_request_payload = job.get("job_request_payload", {})

                # Parse job_request_payload if it's a string (JSON)
                if isinstance(job_request_payload, str):
                    try:
                        import json
                        job_request_payload = json.loads(job_request_payload)
                    except json.JSONDecodeError:
                        #logger.error(f"[JOB-MATCH] Error parsing job_request_payload as JSON for job {job_id}")
                        job_request_payload = {}

                # Create job notification
                try:
                    notification = JobAvailableMessage(
                        job_id=job_id,
                        job_type=job_type,
                        priority=priority,
                        job_request_payload=job_request_payload
                    )
                except Exception as e:
                    #logger.error(f"[JOB-MATCH] Error creating JobAvailableMessage for job {job_id}: {str(e)}")
                    continue

                # Select the first eligible worker
                selected_worker = eligible_workers[0]

                # Send notification to the selected worker
                try:
                    await self.connection_manager.send_to_worker(selected_worker, notification)
                    notified_workers.add(selected_worker)
                    jobs_broadcast = True
                except Exception as e:
                    logger.error(f"[JOB-MATCH] Error sending notification to worker {selected_worker}: {str(e)}")
            return jobs_broadcast

        except Exception as e:
            logger.error(f"[JOB-MATCH] Error broadcasting pending jobs: {str(e)}")
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
                    # For each cleaned job, notify idle workers about it
                    for job_id, job_data in cleaned_jobs.items():
                        # Create job available notification
                        notification = {
                            "type": "job_available",
                            "job_id": job_id,
                            "job_type": job_data.get("job_type", "unknown"),
                            "priority": int(job_data.get("priority", 0)),
                            "job_request_payload": job_data.get("job_request_payload")
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
        DEPRECATED: Stale worker detection is now handled by ConnectionManager._cleanup_stale_workers
        This task is kept temporarily for backwards compatibility but does nothing.
        """
        while True:
            await asyncio.sleep(30)  # Sleep to avoid busy loop
            
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
        # Connect to Redis async client
        try:
            await self.redis_service.connect_async()
        except Exception as e:
            logger.error(f"Failed to connect to Redis async client: {str(e)}")
            return

        # Define job update message handler
        async def handle_job_update(message):
            try:
                # Parse message data
                data = json.loads(message["data"])
                job_id = data.get("job_id")
                message_type = data.get("type")
                status = data.get("status")
                                
                if job_id:
                    # [2025-05-20T20:55:00-04:00] Check if this is a job completion message
                    if status == "completed" and message_type == "update_job_progress":
                        
                        await self.connection_manager.send_job_update(job_id, data)
                        
                        # Get the result data from Redis after ensuring it's stored
                        job_data = self.redis_service.get_job_status(job_id)
                        
                        result = {}
                        
                        if job_data and "result" in job_data:
                            stored_result = job_data["result"]
                            
                            # Process the result based on its type
                            try:
                                if isinstance(stored_result, dict):
                                    # If it's already a dictionary, use it directly
                                    result = stored_result
                                elif isinstance(stored_result, bytes):
                                    # If it's bytes, decode to string first
                                    decoded = stored_result.decode('utf-8')
                                    # Then parse the string as JSON
                                    result = json.loads(decoded)
                                elif isinstance(stored_result, str):
                                    # If it's a string, parse it as JSON
                                    result = json.loads(stored_result)
                                else:
                                    logger.error(f"[JOB-COMPLETE] Unexpected result type: {type(stored_result).__name__}")
                                    result = stored_result
                                
                            except Exception as e:
                                logger.error(f"[JOB-COMPLETE] Error processing result: {str(e)}")
                                logger.exception("[JOB-COMPLETE] Complete stack trace:")
                        else:
                            logger.error(f"[JOB-COMPLETE] No result found in Redis for job {job_id}")
                            if job_data:
                                logger.error(f"[JOB-COMPLETE] Available job_data keys: {list(job_data.keys())}")
                        
                        # Create and send the complete_job message with the result data
                        complete_job_message = {
                            "type": "complete_job",
                            "job_id": job_id,
                            "status": "completed",
                            "priority": None,
                            "position": None,
                            "result": result,
                            "timestamp": time.time()
                        }
                        
                        # Send the complete_job message directly
                        success = await self.connection_manager.send_job_update(job_id, complete_job_message)
                    else:
                        # For non-completion messages, just forward them as before
                        logger.error(f"[JOB-UPDATE] Forwarding non-completion message for job {job_id}")
                        await self.connection_manager.send_job_update(job_id, data)
            except Exception as e:
                logger.error(f"Error handling Redis job update message: {str(e)}")
                logger.exception("Complete stack trace:")

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
