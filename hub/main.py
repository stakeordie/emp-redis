#!/usr/bin/env python3
# Main entry point for the core WebSocket-based Queue API
# [2025-05-20T10:41:50-04:00] Added REST API endpoint for job submission
import os
import asyncio
import uvicorn
import uuid
from fastapi import FastAPI, Body, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
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
    payload: Dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    job_id: Optional[str] = None

@app.get("/")
def read_root():
    """Root endpoint for health check"""
    return {"status": "ok", "message": "WebSocket Queue API is running"}

@app.post("/api/jobs")
async def submit_job(job_data: JobSubmitRequest = Body(...)):
    """
    Submit a job via REST API
    
    This endpoint allows submitting jobs to the Redis queue system via HTTP POST
    instead of WebSocket. The job will be processed the same way as WebSocket-submitted jobs.
    
    Returns:
        dict: Job submission result with job_id
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
        logger.info(f"[2025-05-20T10:41:50-04:00] REST API job submitted: {job_id}, type: {job_data.job_type}")
        
        # Return success response
        return {
            "success": True,
            "job_id": job_id,
            "message": f"Job submitted successfully with ID: {job_id}"
        }
    
    except Exception as e:
        logger.error(f"[2025-05-20T10:41:50-04:00] Error submitting job via REST API: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Run the application
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=False)
