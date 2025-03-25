#!/usr/bin/env python3
# Simulation connector for the EmProps Redis Worker
import os
import asyncio
from typing import Dict, Any, Optional, Union, Callable

from connector_interface import ConnectorInterface
from core.utils.logger import logger

class SimulationConnector(ConnectorInterface):
    """Connector for simulating job processing"""
    
    def __init__(self):
        """Initialize the simulation connector"""
        # Get configuration from environment variables with SIMULATION_ prefix
        self.job_type = os.environ.get("SIMULATION_JOB_TYPE", "simulation")
        self.processing_time = int(os.environ.get("SIMULATION_PROCESSING_TIME", "10"))
        self.steps = int(os.environ.get("SIMULATION_STEPS", "5"))
        
        # Log configuration
        logger.info(f"[SIMULATION] Connector configuration:")
        logger.info(f"[SIMULATION] Job type: {self.job_type}")
        logger.info(f"[SIMULATION] Processing time: {self.processing_time} seconds")
        logger.info(f"[SIMULATION] Steps: {self.steps}")
    
    async def initialize(self) -> bool:
        """Initialize the connector
        
        Returns:
            bool: True if initialization was successful, False otherwise
        """
        logger.info(f"[SIMULATION] Initializing simulation connector")
        logger.info(f"[SIMULATION] Job type: {self.job_type}")
        logger.info(f"[SIMULATION] Processing time: {self.processing_time} seconds")
        logger.info(f"[SIMULATION] Steps: {self.steps}")
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
            "simulation_version": "1.0.0",
            "processing_time": self.processing_time,
            "steps": self.steps
        }
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get the current connection status of the connector
        
        Returns:
            Dict[str, Any]: Connection status information
        """
        # Simulation connector is always connected
        return {
            "connected": True,
            "service": "simulation",
            "details": {
                "job_type": self.job_type,
                "processing_time": self.processing_time,
                "steps": self.steps
            }
        }
    
    async def process_job(self, websocket, job_id: str, payload: Dict[str, Any], send_progress_update) -> Dict[str, Any]:
        """Process a simulated job
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
            job_id: The ID of the job to process
            payload: The job payload
            send_progress_update: Function to send progress updates
            
        Returns:
            Dict[str, Any]: Job result
        """
        try:
            logger.info(f"[SIMULATION] Processing job {job_id}")
            
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
            logger.info(f"[SIMULATION] Job {job_id} completed successfully")
            return {
                "status": "success",
                "output": {
                    "job_id": job_id,
                    "job_type": self.job_type,
                    "processing_time": self.processing_time,
                    "steps": self.steps,
                    "payload_size": len(str(payload)),
                    "result": f"Simulated {self.job_type} job completed successfully"
                }
            }
        except Exception as e:
            logger.error(f"[SIMULATION] Error processing job {job_id}: {str(e)}")
            return {
                "status": "failed",
                "error": str(e)
            }
    
    async def shutdown(self) -> None:
        """Clean up resources when worker is shutting down"""
        logger.info("[SIMULATION] Shutting down simulation connector")
        # No resources to clean up
        logger.info("[SIMULATION] Simulation connector shut down")
