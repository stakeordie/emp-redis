#!/usr/bin/env python3
# Simulation connector for the EmProps Redis Worker
import os
import asyncio
from typing import Dict, Any, Optional, Union, Callable

# Try direct imports first (for Docker container)
try:
    from connector_interface import ConnectorInterface
except ImportError:
    # Fall back to package imports (for local development)
    from worker.connector_interface import ConnectorInterface
from core.utils.logger import logger

class SimulationConnector(ConnectorInterface):
    """Connector for simulating job processing"""
    
    # Set the connector name to match the environment variable
    # Updated: 2025-04-07T15:52:00-04:00
    connector_name = "simulation"
    
    # Version identifier to verify code deployment
    VERSION = "2025-04-04-19:36-connector-details-update"
    
    def __init__(self):
        """Initialize the simulation connector"""
        # Get configuration from environment variables (support both namespaced and non-namespaced)
        self.job_type = os.environ.get("WORKER_SIMULATION_JOB_TYPE", os.environ.get("SIMULATION_JOB_TYPE", "simulation"))
        self.processing_time = int(os.environ.get("WORKER_SIMULATION_PROCESSING_TIME", os.environ.get("SIMULATION_PROCESSING_TIME", "10")))
        self.steps = int(os.environ.get("WORKER_SIMULATION_STEPS", os.environ.get("SIMULATION_STEPS", "5")))
        
        # Log which variables we're using
        logger.info(f"[SIMULATION] Using environment variables:")
        logger.info(f"[SIMULATION] WORKER_SIMULATION_JOB_TYPE/SIMULATION_JOB_TYPE: {self.job_type}")
        logger.info(f"[SIMULATION] WORKER_SIMULATION_PROCESSING_TIME/SIMULATION_PROCESSING_TIME: {self.processing_time}")
        logger.info(f"[SIMULATION] WORKER_SIMULATION_STEPS/SIMULATION_STEPS: {self.steps}")
        
        # Log configuration
        logger.info(f"[SIMULATION] Connector configuration:")
        logger.info(f"[SIMULATION] Job type: {self.job_type}")
        logger.info(f"[SIMULATION] Processing time: {self.processing_time} seconds")
        logger.info(f"[SIMULATION] Steps: {self.steps}")
        
        # Job tracking
        self.current_job_id = None
    
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
            },
            "current_job_id": self.current_job_id,
            "version": self.VERSION  # Include version to verify code deployment
        }
    
    def is_processing_job(self, job_id: str) -> bool:
        """Check if this connector is currently processing the specified job
        
        Args:
            job_id (str): The ID of the job to check
            
        Returns:
            bool: True if this connector is processing the job, False otherwise
        """
        return self.current_job_id == job_id
    
    async def process_job(self, websocket, job_id: str, payload: Dict[str, Any], send_progress_update) -> Dict[str, Any]:
        """Process a job
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
            job_id: The ID of the job to process
            payload: The job payload
            send_progress_update: Function to send progress updates
            
        Returns:
            Dict[str, Any]: Job result
        """
        try:
            # Set current job ID for tracking
            self.current_job_id = job_id
            logger.info(f"[SIMULATION] Processing job {job_id}")
            
            # Send initial progress update with version information
            version_message = f"Starting {self.job_type} job [version: {self.VERSION}]"
            await send_progress_update(job_id, 0, "started", version_message)
            
            # Simulate job processing with progress updates
            step_time = self.processing_time / self.steps
            for step in range(1, self.steps + 1):
                # Calculate progress percentage
                progress = int((step / self.steps) * 100)
                
                # Send progress update with version information
                status = "finalizing" if step == self.steps else "processing"
                version_message = f"Step {step}/{self.steps}: Processing at {progress}% [version: {self.VERSION}]"
                await send_progress_update(job_id, progress, status, version_message)
                
                # Simulate processing time
                await asyncio.sleep(step_time)
                
                # Send heartbeat every other step
                if step % 2 == 0:
                    # Include version in the message field for visibility in client
                    version_message = f"Heartbeat during step {step} [version: {self.VERSION}]"
                    await send_progress_update(job_id, -1, "heartbeat", version_message)
            
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
        finally:
            # Clear current job ID when done
            logger.info(f"[SIMULATION] Completed job {job_id}")
            self.current_job_id = None
    
    async def shutdown(self) -> None:
        """Clean up resources when worker is shutting down"""
        logger.info("[SIMULATION] Shutting down simulation connector")
        # No resources to clean up
        logger.info("[SIMULATION] Simulation connector shut down")
