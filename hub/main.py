#!/usr/bin/env python3
# Main entry point for the core WebSocket-based Queue API
# [2025-05-20T10:41:50-04:00] Added REST API endpoint for job submission
import os
import sys
import uuid
import time
import asyncio
import uvicorn
import logging
from typing import Dict, Any, Optional, List, Union
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

import sys
import os

# Add parent directory to path to find core module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.message_broker import MessageBroker
from core.redis_service import RedisService

from core.utils.logger import logger

logger.info("IT WORKS")

# FastAPI startup and shutdown event handling
@asynccontextmanager
async def lifespan(app: FastAPI):
    
    # Create MessageBroker instance with all required components
    message_broker = MessageBroker()
    
    # Initialize WebSocket connections
    message_broker.init_connections(app)
    
    # Start background tasks (including Redis pub/sub listener)
    await message_broker.start_background_tasks()
    
    yield
    
    # Shutdown tasks
    try:
        await message_broker.stop_background_tasks()
    except asyncio.CancelledError:
        pass
    
    # Close Redis connections
    redis_service = RedisService()
    await redis_service.close_async()

# Initialize FastAPI with lifespan manager
app = FastAPI(title="WebSocket Queue API", lifespan=lifespan)

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

# Define request models for job submission
class JobSubmitRequest(BaseModel):
    job_type: str
    payload: Dict[str, Any]
    priority: int = 0
    job_id: Optional[str] = None
    # [2025-05-20T11:34:47-04:00] Added wait parameter for synchronous requests
    wait: bool = False
    # Maximum time to wait for job completion in seconds (only used if wait=True)
    timeout: int = 300

# [2025-05-20T11:34:47-04:00] Added model for job status response
class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    job_type: Optional[str] = None
    client_id: Optional[str] = None
    worker_id: Optional[str] = None
    created_at: Optional[str] = None
    claimed_at: Optional[str] = None
    completed_at: Optional[str] = None
    position: Optional[int] = None
    progress: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

@app.get("/")
def read_root():
    """Root endpoint for health check"""
    return {"status": "ok", "message": "WebSocket Queue API is running"}

@app.post("/api/jobs", response_model=Union[Dict[str, Any], JobStatusResponse])
async def submit_job(job_data: JobSubmitRequest = Body(...)):
    """
    [2025-05-20T11:34:47-04:00] Submit a job via REST API with synchronous or asynchronous processing
    
    This endpoint allows submitting jobs to the Redis queue system via HTTP POST
    instead of WebSocket. The job will be processed the same way as WebSocket-submitted jobs.
    
    If wait=True is specified, the endpoint will wait for the job to complete and return the final result.
    If wait=False (default), the endpoint will return immediately with the job ID.
    
    Args:
        job_data: Job submission data including type, payload, priority, and wait flag
        
    Returns:
        Union[Dict[str, Any], JobStatusResponse]: 
            - If wait=False: Basic job submission result with job_id
            - If wait=True: Complete job status including result when job completes
    """
    try:
        # Get Redis service instance
        redis_service = RedisService()
        
        # Generate job_id if not provided
        job_id = job_data.job_id or f"job-rest-{uuid.uuid4()}"
        
        # Add job to Redis
        success = redis_service.add_job(
            job_id=job_id,
            job_type=job_data.job_type,
            job_request_payload=job_data.payload,
            priority=job_data.priority,
            client_id="rest-api-client"
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to add job to queue")
        
        # Log job submission
        logger.info(f"[2025-05-20T11:34:47-04:00] REST API job submitted: {job_id}, type: {job_data.job_type}, wait: {job_data.wait}")
        
        # If wait=False, return immediately with job ID
        if not job_data.wait:
            return {
                "success": True,
                "job_id": job_id,
                "message": f"Job submitted successfully with ID: {job_id}"
            }
        
        # If wait=True, poll for job completion
        logger.info(f"[2025-05-20T11:34:47-04:00] Waiting for job {job_id} to complete (timeout: {job_data.timeout}s)")
        
        # Set start time for timeout calculation
        start_time = time.time()
        
        # Poll until job completes or timeout is reached
        while time.time() - start_time < job_data.timeout:
            # Get current job status
            job_status = redis_service.get_job_status(job_id)
            
            if job_status is None:
                raise HTTPException(status_code=404, detail=f"Job with ID {job_id} not found")
            
            # Check if job is completed or failed
            if job_status.get('status') in ['completed', 'failed']:
                # Convert job_status to JobStatusResponse model
                response_data = JobStatusResponse(
                    job_id=job_id,
                    status=job_status.get('status', 'unknown'),
                    job_type=job_status.get('job_type'),
                    client_id=job_status.get('client_id'),
                    worker_id=job_status.get('worker_id'),
                    created_at=job_status.get('created_at'),
                    claimed_at=job_status.get('claimed_at'),
                    completed_at=job_status.get('completed_at'),
                    position=job_status.get('position'),
                    progress=float(job_status.get('progress', 0)) if job_status.get('progress') is not None else None,
                    result=job_status.get('result'),
                    error=job_status.get('error')
                )
                
                return response_data
            
            # Wait before polling again (to avoid hammering Redis)
            await asyncio.sleep(0.5)
        
        # If we get here, the job timed out
        # Return the current status with a timeout indicator
        job_status = redis_service.get_job_status(job_id)
        
        if job_status is None:
            raise HTTPException(status_code=404, detail=f"Job with ID {job_id} not found")
        
        # Convert job_status to JobStatusResponse model with timeout indicator
        response_data = JobStatusResponse(
            job_id=job_id,
            status=job_status.get('status', 'unknown'),
            job_type=job_status.get('job_type'),
            client_id=job_status.get('client_id'),
            worker_id=job_status.get('worker_id'),
            created_at=job_status.get('created_at'),
            claimed_at=job_status.get('claimed_at'),
            completed_at=job_status.get('completed_at'),
            position=job_status.get('position'),
            progress=float(job_status.get('progress', 0)) if job_status.get('progress') is not None else None,
            result=job_status.get('result'),
            error=f"Timeout: Job did not complete within {job_data.timeout} seconds"
        )
        
        return response_data
    
    except Exception as e:
        logger.error(f"[2025-05-20T11:34:47-04:00] Error submitting job via REST API: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """
    [2025-05-20T11:34:47-04:00] Get the status of a job by its ID
    
    This endpoint allows checking the status of a job that was submitted via REST API
    or WebSocket. It returns detailed information about the job including its current
    status, progress, and result if available.
    
    Args:
        job_id: The ID of the job to check
        
    Returns:
        JobStatusResponse: Detailed job status information
        
    Raises:
        HTTPException: If the job is not found or if there's an error retrieving the status
    """
    try:
        # Get Redis service instance
        redis_service = RedisService()
        
        # Get job status from Redis
        job_data = redis_service.get_job_status(job_id)
        
        # If job not found, return 404
        if job_data is None:
            raise HTTPException(status_code=404, detail=f"Job with ID {job_id} not found")
        
        # Log job status request
        logger.info(f"[2025-05-20T11:34:47-04:00] REST API job status requested: {job_id}, status: {job_data.get('status', 'unknown')}")
        
        # Convert job_data to JobStatusResponse model
        # This ensures we only return the fields defined in the model
        response_data = JobStatusResponse(
            job_id=job_id,
            status=job_data.get('status', 'unknown'),
            job_type=job_data.get('job_type'),
            client_id=job_data.get('client_id'),
            worker_id=job_data.get('worker_id'),
            created_at=job_data.get('created_at'),
            claimed_at=job_data.get('claimed_at'),
            completed_at=job_data.get('completed_at'),
            position=job_data.get('position'),
            progress=float(job_data.get('progress', 0)) if job_data.get('progress') is not None else None,
            result=job_data.get('result'),
            error=job_data.get('error')
        )
        
        return response_data
    
    except HTTPException as he:
        # Re-raise HTTP exceptions
        raise he
    except Exception as e:
        logger.error(f"[2025-05-20T11:34:47-04:00] Error getting job status via REST API: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Run the application
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=False)
