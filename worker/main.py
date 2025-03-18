#!/usr/bin/env python3
# Worker service for the EmProps Redis system
import os
import sys
import json
import uuid
import time
import asyncio
import websockets
from typing import Dict, Any, Optional, List, Union, cast

# Import core modules for message handling
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
    RegisterWorkerMessage  # Added for worker registration
    # SubscribeJobNotificationsMessage has been removed - functionality now in RegisterWorkerMessage
)
from core.utils.logger import logger

# Configuration from environment variables
REDIS_API_HOST = os.environ.get("REDIS_API_HOST", "localhost")
REDIS_API_PORT = int(os.environ.get("REDIS_API_PORT", "8001"))
WORKER_ID = os.environ.get("WORKER_ID", f"worker-{uuid.uuid4().hex[:8]}")
# Reduced heartbeat interval for more frequent updates
HEARTBEAT_INTERVAL = int(os.environ.get("HEARTBEAT_INTERVAL", "20"))
# Authentication token
WEBSOCKET_AUTH_TOKEN = os.environ.get("WEBSOCKET_AUTH_TOKEN", "")

# WebSocket connection to Redis Hub
base_url = f"ws://{REDIS_API_HOST}:{REDIS_API_PORT}/ws/worker/{WORKER_ID}"
# Add authentication token if provided
REDIS_HUB_WS_URL = f"{base_url}?token={WEBSOCKET_AUTH_TOKEN}" if WEBSOCKET_AUTH_TOKEN else base_url

# Worker capabilities
WORKER_CAPABILITIES = {
    "gpu": True,
    "cpu": True,
    "memory": "16GB",
    "version": "1.0.0",
    "supported_job_types": ["image_processing", "text_generation", "data_analysis"]
}

# Initialize MessageModels for message parsing
message_models = MessageModels()

# Track worker state
worker_state = {
    "status": "idle",
    "current_job_id": None
}

async def connect_to_hub():
    """Connect to Redis Hub and handle messages"""
    logger.info(f"[WORKER] Connecting to Redis Hub at {REDIS_HUB_WS_URL}")
    
    while True:
        try:
            async with websockets.connect(REDIS_HUB_WS_URL) as websocket:
                logger.info(f"[WORKER] Connected to Redis Hub as {WORKER_ID}")
                
                # Send registration message (combines status, capabilities, and subscription)
                register_message = RegisterWorkerMessage(
                    worker_id=WORKER_ID,
                    capabilities=WORKER_CAPABILITIES,
                    subscribe_to_jobs=True,
                    status="idle"
                )
                await websocket.send(register_message.model_dump_json())
                logger.info(f"[WORKER] Registered with Redis Hub")
                
                # Start heartbeat task
                heartbeat_task = asyncio.create_task(send_heartbeat(websocket))
                
                # Main message loop
                try:
                    while True:
                        message_raw = await websocket.recv()
                        # Convert bytes to str if needed
                        message_json = message_raw.decode('utf-8') if isinstance(message_raw, bytes) else str(message_raw)
                        await handle_message(websocket, message_json)
                except Exception as e:
                    logger.error(f"[WORKER] Error processing message: {str(e)}")
                finally:
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass
        
        except Exception as e:
            logger.error(f"[WORKER] Connection error: {str(e)}")
            logger.info(f"[WORKER] Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

async def send_heartbeat(websocket):
    """Send periodic heartbeat messages to the hub"""
    while True:
        try:
            # Use the proper WorkerHeartbeatMessage model
            heartbeat_message = WorkerHeartbeatMessage(
                worker_id=WORKER_ID,
                status=worker_state["status"],
                load=0.0
            )
            await websocket.send(heartbeat_message.model_dump_json())
            logger.debug(f"[WORKER] Sent heartbeat")
            await asyncio.sleep(HEARTBEAT_INTERVAL)
        except Exception as e:
            logger.error(f"[WORKER] Error sending heartbeat: {str(e)}")
            break

async def handle_message(websocket, message_json: str):
    """Handle incoming messages from the hub using core message models"""
    try:
        # Parse the message using MessageModels
        message_data = json.loads(message_json)
        message_obj = message_models.parse_message(message_data)
        
        if not message_obj:
            logger.warning(f"[WORKER] Invalid message format: {message_json[:100]}...")
            return
        
        message_type = message_obj.type
        logger.debug(f"[WORKER] Received message of type: {message_type}")
        
        if message_type == MessageType.CONNECTION_ESTABLISHED:
            logger.info(f"[WORKER] Connection established: {getattr(message_obj, 'message', '')}")
        
        elif message_type == MessageType.JOB_AVAILABLE:
            # Handle job notification
            # Ensure we have a JobAvailableMessage or compatible dict
            if hasattr(message_obj, 'job_id') and hasattr(message_obj, 'job_type'):
                # Cast to Any to avoid type checking issues
                await handle_job_notification(websocket, cast(Any, message_obj))
            else:
                logger.warning(f"[WORKER] Received JOB_AVAILABLE message with invalid format")
        
        elif message_type == MessageType.JOB_ASSIGNED:
            # Process assigned job
            await process_job(websocket, message_obj)
        
        elif message_type == MessageType.WORKER_HEARTBEAT:
            logger.debug(f"[WORKER] Heartbeat acknowledged")
            
        elif message_type == MessageType.JOB_COMPLETED_ACK:
            # Handle job completion acknowledgment from the server
            if hasattr(message_obj, 'job_id'):
                job_id = message_obj.job_id
                logger.info(f"[WORKER] Job completion acknowledged by server: {job_id}")
            else:
                logger.warning(f"[WORKER] Received JOB_COMPLETED_ACK message with invalid format")
        
        elif message_type == MessageType.WORKER_REGISTERED:
            # Handle worker registration confirmation
            worker_id = getattr(message_obj, 'worker_id', WORKER_ID)
            logger.info(f"[WORKER] Worker registration confirmed: {worker_id}")
            # No further action needed, this is just an acknowledgment
        
        elif message_type == MessageType.ERROR:
            # Handle error messages from the server
            error_text = getattr(message_obj, 'error', 'Unknown error')
            logger.warning(f"[WORKER] Received error from server: {error_text}")
            
            # If we're in a non-idle state and the error is related to job claiming,
            # reset the worker state to idle
            if worker_state["status"] != "idle" and "claim job" in error_text.lower():
                logger.info(f"[WORKER] Resetting worker state to idle after claim error")
                worker_state["status"] = "idle"
                worker_state["current_job_id"] = None
        
        else:
            logger.warning(f"[WORKER] Unhandled message type: {message_type}")
    
    except json.JSONDecodeError:
        logger.error(f"[WORKER] Invalid JSON: {message_json[:100]}...")
    except Exception as e:
        logger.error(f"[WORKER] Error handling message: {str(e)}")

async def handle_job_notification(websocket, job_notification: Any):
    """Handle job notification and decide whether to claim the job"""
    if worker_state["status"] != "idle":
        logger.info(f"[WORKER] Ignoring job notification - worker is busy")
        return
    
    # Extract job details safely with fallbacks
    job_id = getattr(job_notification, 'job_id', None)
    if job_id is None:
        logger.error(f"[WORKER] Job notification missing job_id")
        return
        
    job_type = getattr(job_notification, 'job_type', 'unknown')
    priority = getattr(job_notification, 'priority', 0)
    
    logger.info(f"[WORKER] Received job notification - job_id: {job_id}, type: {job_type}, priority: {priority}")
    
    # Check if worker supports this job type
    supported_job_types = WORKER_CAPABILITIES.get("supported_job_types", [])
    
    # Ensure job_type is a string and supported_job_types is a list
    if isinstance(job_type, str) and isinstance(supported_job_types, list) and job_type in list(supported_job_types):
        logger.info(f"[WORKER] Job type '{job_type}' is supported, claiming job {job_id}")
        await claim_job(websocket, job_id)
    else:
        logger.info(f"[WORKER] Job type '{job_type}' is not supported, ignoring")

async def claim_job(websocket, job_id: str):
    """Send a claim job request to the server"""
    try:
        # Add debug logging to show worker state before claiming
        logger.debug(f"[WORKER] Worker state before claiming job {job_id}: {worker_state}")
        
        # Worker remains in idle state until job is assigned
        # No state change here - we'll wait for JOB_ASSIGNED message
        
        # Create claim job message
        claim_message = ClaimJobMessage(
            worker_id=WORKER_ID,
            job_id=job_id
        )
        
        # Send claim request
        logger.info(f"[WORKER] Sending claim request for job {job_id}")
        await websocket.send(claim_message.model_dump_json())
        
    except Exception as e:
        logger.error(f"[WORKER] Error claiming job {job_id}: {str(e)}")

async def send_progress_update(websocket, job_id: str, progress: int, status: str = "processing", message: Optional[str] = None):
    """Send a progress update for a job
    
    Args:
        websocket: The WebSocket connection to send the update through
        job_id: The ID of the job being processed
        progress: Progress percentage (0-100)
        status: Current job status (default: "processing")
        message: Optional status message
    """
    try:
        # Create progress update message
        progress_message = UpdateJobProgressMessage(
            job_id=job_id,
            worker_id=WORKER_ID,
            progress=progress,
            status=status,
            message=message
        )
        
        # Send the progress update
        await websocket.send(progress_message.model_dump_json())
        logger.debug(f"[WORKER] Sent progress update for job {job_id}: {progress}% - {message if message else status}")
        
    except Exception as e:
        logger.error(f"[WORKER] Error sending progress update for job {job_id}: {str(e)}")

async def process_job(websocket, job_message: Union[BaseMessage, Dict]):
    """Process an assigned job"""
    # Extract job details from message object
    if isinstance(job_message, dict):
        job_id = job_message.get("job_id")
        job_type = job_message.get("job_type", "unknown")
        payload = job_message.get("job_request_payload", {})
    else:
        # Safely extract attributes with fallbacks
        # Using explicit try/except to handle attribute access safely
        try:
            job_id = job_message.job_id if hasattr(job_message, "job_id") else None
        except (AttributeError, TypeError):
            job_id = None
            
        try:
            job_type = job_message.job_type if hasattr(job_message, "job_type") else "unknown"
        except (AttributeError, TypeError):
            job_type = "unknown"
            
        try:
            payload = job_message.job_request_payload if hasattr(job_message, "job_request_payload") else {}
        except (AttributeError, TypeError):
            payload = {}
    
    # Ensure job_id is not None
    if job_id is None:
        logger.error(f"[WORKER] Cannot process job: missing job_id")
        return
    
    logger.info(f"[WORKER] Processing job {job_id} of type {job_type}")
    
    # Update worker state
    worker_state["status"] = "busy"
    worker_state["current_job_id"] = job_id
    
    # Update status to busy
    busy_status = WorkerStatusMessage(
        worker_id=WORKER_ID,
        status="busy",
        capabilities={"job_id": job_id}
    )
    await websocket.send(busy_status.model_dump_json())
    
    try:
        # Simulate job processing based on job type
        logger.info(f"[WORKER] Starting job processing for {job_id}")
        
        # Send initial progress update
        await send_progress_update(websocket, job_id, 0, "started", f"Starting {job_type} job")
        
        # Different processing time and progress updates based on job type
        if job_type == "image_processing":

            logger.debug(f"[IMAGE JOB in PROGRESS] Processing image job {job_id}")
            # Image processing simulation with progress updates
            total_steps = 5
            for step in range(1, total_steps + 1):
                # Calculate progress percentage
                progress = int((step / total_steps) * 100)
                
                # Send progress update with appropriate message
                if step == 1:
                    await send_progress_update(websocket, job_id, progress, "processing", "Loading image data")
                elif step == 2:
                    await send_progress_update(websocket, job_id, progress, "processing", "Applying filters")
                elif step == 3:
                    await send_progress_update(websocket, job_id, progress, "processing", "Processing pixels")
                elif step == 4:
                    await send_progress_update(websocket, job_id, progress, "processing", "Optimizing output")
                elif step == 5:
                    await send_progress_update(websocket, job_id, progress, "finalizing", "Finalizing image")
                
                # Simulate processing time for this step
                await asyncio.sleep(1)
            
            result = {"status": "success", "output": f"Processed image in job {job_id}"}
            
        elif job_type == "text_generation":
            # Text generation simulation with progress updates
            total_steps = 3
            for step in range(1, total_steps + 1):
                progress = int((step / total_steps) * 100)
                
                if step == 1:
                    await send_progress_update(websocket, job_id, progress, "processing", "Analyzing input text")
                elif step == 2:
                    await send_progress_update(websocket, job_id, progress, "processing", "Generating content")
                elif step == 3:
                    await send_progress_update(websocket, job_id, progress, "finalizing", "Formatting output")
                
                await asyncio.sleep(1)
            
            result = {"status": "success", "output": f"Generated text for job {job_id}"}
            
        elif job_type == "data_analysis":
            # Data analysis simulation with progress updates
            total_steps = 7
            for step in range(1, total_steps + 1):
                progress = int((step / total_steps) * 100)
                
                if step == 1:
                    await send_progress_update(websocket, job_id, progress, "processing", "Loading dataset")
                elif step == 2:
                    await send_progress_update(websocket, job_id, progress, "processing", "Cleaning data")
                elif step == 3:
                    await send_progress_update(websocket, job_id, progress, "processing", "Normalizing values")
                elif step == 4:
                    await send_progress_update(websocket, job_id, progress, "processing", "Running statistical analysis")
                elif step == 5:
                    await send_progress_update(websocket, job_id, progress, "processing", "Generating visualizations")
                elif step == 6:
                    await send_progress_update(websocket, job_id, progress, "processing", "Compiling results")
                elif step == 7:
                    await send_progress_update(websocket, job_id, progress, "finalizing", "Preparing final report")
                
                await asyncio.sleep(1)
            
            result = {"status": "success", "output": f"Analyzed data in job {job_id}"}
            
        else:
            # Default job simulation with simple progress updates
            for progress in [25, 50, 75, 100]:
                await send_progress_update(websocket, job_id, progress, "processing", f"Processing at {progress}%")
                await asyncio.sleep(0.5)
            
            result = {"status": "success", "output": f"Completed job {job_id}"}
        
        # Send final 100% progress update
        await send_progress_update(websocket, job_id, 100, "completed", "Job completed successfully")
        
        logger.info(f"[WORKER] Job {job_id} completed successfully")
        
        # Send job completion message
        job_id_str = str(job_id) if job_id is not None else "unknown_job"
        complete_message = CompleteJobMessage(
            job_id=job_id_str,  # Ensure job_id is a valid string
            worker_id=WORKER_ID,
            result=result
        )
        await websocket.send(complete_message.model_dump_json())
        
    except Exception as e:
        logger.error(f"[WORKER] Error processing job {job_id}: {str(e)}")
        
        # Send job failure message
        job_id_str = str(job_id) if job_id is not None else "unknown_job"
        fail_message = CompleteJobMessage(
            job_id=job_id_str,  # Ensure job_id is a valid string
            worker_id=WORKER_ID,
            result={
                "status": "failed",
                "error": str(e)
            }
        )
        await websocket.send(fail_message.model_dump_json())
    
    finally:
        # Reset worker state
        worker_state["status"] = "idle"
        worker_state["current_job_id"] = None
        
        # Update status back to idle
        idle_status = WorkerStatusMessage(
            worker_id=WORKER_ID,
            status="idle"
        )
        await websocket.send(idle_status.model_dump_json())
        logger.info(f"[WORKER] Worker status reset to idle")

if __name__ == "__main__":
    try:
        logger.info(f"[WORKER] Starting worker {WORKER_ID}")
        # Run the worker
        asyncio.run(connect_to_hub())
    except KeyboardInterrupt:
        logger.info("[WORKER] Worker shutting down...")
    except Exception as e:
        logger.error(f"[WORKER] Unexpected error: {str(e)}")
        sys.exit(1)
