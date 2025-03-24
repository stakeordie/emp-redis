#!/usr/bin/env python3
# Image Processing connector for the EmProps Redis Worker
import os
import asyncio
from typing import Dict, Any, Optional, Union, Callable

from connector_interface import ConnectorInterface
from core.utils.logger import logger

class ImageProcessingConnector(ConnectorInterface):
    """Connector for image processing jobs"""
    
    def __init__(self):
        """Initialize the image processing connector"""
        # Get configuration from environment variables with IMAGE_PROCESSING_ prefix
        self.job_type = os.environ.get("IMAGE_PROCESSING_JOB_TYPE", "image_processing")
        self.processing_time = int(os.environ.get("IMAGE_PROCESSING_PROCESSING_TIME", "10"))
        self.steps = int(os.environ.get("IMAGE_PROCESSING_STEPS", "5"))
        
        # Log configuration
        logger.info(f"[IMAGE_PROCESSING] Connector configuration:")
        logger.info(f"[IMAGE_PROCESSING] Job type: {self.job_type}")
        logger.info(f"[IMAGE_PROCESSING] Processing time: {self.processing_time} seconds")
        logger.info(f"[IMAGE_PROCESSING] Steps: {self.steps}")
    
    def initialize(self) -> bool:
        """Initialize the connector
        
        Returns:
            bool: True if initialization was successful, False otherwise
        """
        logger.info(f"[IMAGE_PROCESSING] Initializing image processing connector")
        logger.info(f"[IMAGE_PROCESSING] Job type: {self.job_type}")
        logger.info(f"[IMAGE_PROCESSING] Processing time: {self.processing_time} seconds")
        logger.info(f"[IMAGE_PROCESSING] Steps: {self.steps}")
        return True
    
    def get_job_type(self) -> str:
        """Get the job type that this connector handles
        
        Returns:
            str: The job type string
        """
        return self.job_type
    
    def get_capabilities(self) -> Dict[str, Any]:
        """Get connector-specific capabilities
        
        Returns:
            Dict[str, Any]: Capabilities dictionary to be merged with worker capabilities
        """
        return {
            "image_processing_version": "1.0.0",
            "processing_time": self.processing_time,
            "steps": self.steps
        }
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get the current connection status of the connector
        
        Returns:
            Dict[str, Any]: Connection status information
        """
        # Image processing connector is always connected
        return {
            "connected": True,
            "service": "image_processing",
            "details": {
                "job_type": self.job_type,
                "processing_time": self.processing_time,
                "steps": self.steps
            }
        }
    
    async def process_job(self, websocket, job_id: str, payload: Dict[str, Any], send_progress_update) -> Dict[str, Any]:
        """Process an image processing job
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
            job_id: The ID of the job to process
            payload: The job payload
            send_progress_update: Function to send progress updates
            
        Returns:
            Dict[str, Any]: Job result
        """
        try:
            logger.info(f"[IMAGE_PROCESSING] Processing job {job_id}")
            
            # Send initial progress update
            await send_progress_update(job_id, 0, "started", f"Starting {self.job_type} job")
            
            # Simulate job processing with progress updates
            step_time = self.processing_time / self.steps
            for step in range(1, self.steps + 1):
                # Calculate progress percentage
                progress = int((step / self.steps) * 100)
                
                # Send progress update
                status = "finalizing" if step == self.steps else "processing"
                await send_progress_update(job_id, progress, status, f"Step {step}/{self.steps}: Processing at {progress}%")
                
                # Simulate processing time
                await asyncio.sleep(step_time)
            
            # Return result
            logger.info(f"[IMAGE_PROCESSING] Job {job_id} completed successfully")
            return {
                "status": "success",
                "output": {
                    "job_id": job_id,
                    "job_type": self.job_type,
                    "processing_time": self.processing_time,
                    "steps": self.steps,
                    "payload_size": len(str(payload)),
                    "result": f"Image processing job completed successfully"
                }
            }
        except Exception as e:
            logger.error(f"[IMAGE_PROCESSING] Error processing job {job_id}: {str(e)}")
            return {
                "status": "failed",
                "error": str(e)
            }
    
    async def shutdown(self) -> None:
        """Clean up resources when worker is shutting down"""
        logger.info("[IMAGE_PROCESSING] Shutting down image processing connector")
        # No resources to clean up
        logger.info("[IMAGE_PROCESSING] Image processing connector shut down")
