#!/usr/bin/env python3
# Base worker for the EmProps Redis Worker
import os
import sys
import json
import asyncio
import uuid
import websockets
from typing import Dict, List, Any, Optional, Union, cast
from enum import Enum, auto

# Add the parent directory to the Python path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

# Add the current directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Import required modules
from connector_interface import ConnectorInterface
from connector_loader import load_connectors, get_worker_capabilities
from core.utils.logger import logger
from core.message_models import MessageModels, MessageType

class WorkerStatus(Enum):
    """Worker status enum"""
    IDLE = auto()
    BUSY = auto()
    ERROR = auto()

class BaseWorker:
    """Base worker class for the EmProps Redis Worker"""
    
    def __init__(self):
        """Initialize the base worker"""
        # Load environment variables
        self.redis_host = os.environ.get("REDIS_API_HOST", "localhost")
        self.redis_port = int(os.environ.get("REDIS_API_PORT", "8000"))
        self.use_ssl = os.environ.get("USE_SSL", "false").lower() in ("true", "1", "yes")
        self.worker_id = os.environ.get("WORKER_ID", f"worker-{uuid.uuid4()}")
        self.auth_token = os.environ.get("WEBSOCKET_AUTH_TOKEN", "")
        self.heartbeat_interval = int(os.environ.get("HEARTBEAT_INTERVAL", "20"))
        
        # Redis Hub WebSocket URL
        protocol = "wss" if self.use_ssl else "ws"
        self.redis_ws_url = f"{protocol}://{self.redis_host}:{self.redis_port}/ws/worker?token={self.auth_token}"
        
        # Debug prints
        print(f"Debug - REDIS_API_HOST: {self.redis_host}")
        print(f"Debug - REDIS_API_PORT: {self.redis_port}")
        print(f"Debug - USE_SSL: {self.use_ssl}")
        print(f"Debug - Redis WebSocket URL: {self.redis_ws_url}")
        
        # Initialize MessageModels for message parsing
        self.message_models = MessageModels()
        
        # Load connectors
        self.connectors = load_connectors()
        
        # Worker capabilities
        self.capabilities = get_worker_capabilities(self.connectors)
        
        # Worker state
        self.status = WorkerStatus.IDLE
        self.current_job_id = None
    
    def get_connector_statuses(self) -> Dict[str, Any]:
        """Get connection status for all connectors
        
        Returns:
            Dict[str, Any]: Dictionary of connector statuses
        """
        connector_statuses = {}
        for connector in self.connectors:
            try:
                status = connector.get_connection_status()
                connector_statuses[status["service"]] = status
            except Exception as e:
                logger.error(f"Error getting connection status for connector: {str(e)}")
                # Add error status for this connector
                connector_statuses[connector.get_job_type()] = {
                    "connected": False,
                    "service": connector.get_job_type(),
                    "details": {"error": str(e)}
                }
        return connector_statuses
    
    async def send_status_update(self, websocket):
        """Send worker status update to Redis Hub
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
        """
        try:
            # Get connection status for all connectors
            connector_statuses = self.get_connector_statuses()
            
            # Create worker status message
            status_message = self.message_models.create_worker_status_message(
                worker_id=self.worker_id,
                status=self.status.name.lower(),
                capabilities={
                    **self.capabilities,
                    "connector_statuses": connector_statuses
                }
            )
            
            # Send status message
            await websocket.send(json.dumps(status_message))
            logger.debug(f"Sent status update with connector statuses")
        except Exception as e:
            logger.error(f"Error sending status update: {str(e)}")
    
    async def send_heartbeat(self, websocket):
        """Send heartbeat messages to keep the connection alive
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
        """
        status_interval = 5  # Send full status every 5 heartbeats
        counter = 0
        
        while True:
            try:
                # Increment counter
                counter += 1
                
                # Every status_interval heartbeats, send a full status update
                if counter % status_interval == 0:
                    await self.send_status_update(websocket)
                
                # Create heartbeat message
                heartbeat_message = self.message_models.create_heartbeat_message(
                    worker_id=self.worker_id,
                    status=self.status.name.lower(),
                    current_job_id=self.current_job_id
                )
                
                # Send heartbeat message
                await websocket.send(json.dumps(heartbeat_message))
                logger.debug(f"Sent heartbeat: {self.status.name.lower()}")
                
                # Wait for next heartbeat
                await asyncio.sleep(self.heartbeat_interval)
            except Exception as e:
                logger.error(f"Error sending heartbeat: {str(e)}")
                await asyncio.sleep(5)  # Wait before retrying
    
    async def send_progress_update(self, websocket, job_id: str, progress: int, status: str, message: str):
        """Send progress update to Redis Hub
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
            job_id: The ID of the job being processed
            progress: The progress percentage (0-100)
            status: The job status (e.g., "processing", "completed")
            message: A message describing the current progress
        """
        try:
            # Create progress update message
            progress_message = self.message_models.create_progress_update_message(
                worker_id=self.worker_id,
                job_id=job_id,
                progress=progress,
                status=status,
                message=message
            )
            
            # Send progress update message
            await websocket.send(json.dumps(progress_message))
            logger.debug(f"Sent progress update: {progress}% - {message}")
        except Exception as e:
            logger.error(f"Error sending progress update: {str(e)}")
    
    async def handle_job_notification(self, websocket, message_obj):
        """Handle job notification message from Redis Hub
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
            message_obj: The job notification message object
        """
        try:
            # Extract job details
            job_id = message_obj.get("job_id")
            job_type = message_obj.get("job_type")
            
            # Check if we can handle this job type
            if job_type not in self.connectors:
                logger.warning(f"Received job notification for unsupported job type: {job_type}")
                return
            
            # Claim the job
            claim_message = self.message_models.create_job_claim_message(
                worker_id=self.worker_id,
                job_id=job_id
            )
            await websocket.send(json.dumps(claim_message))
            logger.info(f"Claimed job {job_id} of type {job_type}")
            
            # Update worker state
            self.status = WorkerStatus.BUSY
            self.current_job_id = job_id
        except Exception as e:
            logger.error(f"Error handling job notification: {str(e)}")
    
    async def handle_job_assigned(self, websocket, message_obj):
        """Handle job assigned message from Redis Hub
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
            message_obj: The job assigned message object
        """
        try:
            # Extract job details
            job_id = message_obj.get("job_id")
            job_type = message_obj.get("job_type")
            payload = message_obj.get("job_request_payload", {})
            
            logger.info(f"Assigned job {job_id} of type {job_type}")
            
            # Get the appropriate connector for this job type
            connector = self.connectors.get(job_type)
            if connector is None:
                logger.error(f"No connector available for job type: {job_type}")
                
                # Send error progress update
                await self.send_progress_update(
                    websocket, job_id, 0, "error", 
                    f"No connector available for job type: {job_type}"
                )
                
                # Reset worker state
                self.status = WorkerStatus.IDLE
                self.current_job_id = None
                return
            
            # Process the job using the connector
            result = await connector.process_job(
                websocket, job_id, payload, 
                lambda job_id, progress, status, message: self.send_progress_update(websocket, job_id, progress, status, message)
            )
            
            # Send job completion message
            completion_message = self.message_models.create_job_completion_message(
                worker_id=self.worker_id,
                job_id=job_id,
                result=result
            )
            await websocket.send(json.dumps(completion_message))
            logger.info(f"Completed job {job_id}")
            
            # Reset worker state
            self.status = WorkerStatus.IDLE
            self.current_job_id = None
        except Exception as e:
            logger.error(f"Error processing job: {str(e)}")
            
            # Send error progress update
            if self.current_job_id:
                await self.send_progress_update(
                    websocket, self.current_job_id, 0, "error", 
                    f"Error processing job: {str(e)}"
                )
            
            # Reset worker state
            self.status = WorkerStatus.IDLE
            self.current_job_id = None
    
    async def handle_message(self, websocket, message):
        """Handle incoming message from Redis Hub
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
            message: The raw message string
        """
        try:
            # Parse message
            message_obj = json.loads(message)
            message_type = self.message_models.get_message_type(message_obj)
            
            # Handle message based on type
            if message_type == MessageType.JOB_AVAILABLE:
                await self.handle_job_notification(websocket, cast(Any, message_obj))
            elif message_type == MessageType.JOB_ASSIGNED:
                await self.handle_job_assigned(websocket, cast(Any, message_obj))
            elif message_type == MessageType.CONNECTION_ACK:
                logger.info("Connection acknowledged by Redis Hub")
            else:
                logger.debug(f"Received message of type {message_type}: {message}")
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
    
    async def register_worker(self, websocket):
        """Register worker with Redis Hub
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
        """
        try:
            # Create registration message
            registration_message = self.message_models.create_registration_message(
                worker_id=self.worker_id,
                capabilities=self.capabilities
            )
            
            # Send registration message
            await websocket.send(json.dumps(registration_message))
            logger.info(f"Registered worker with ID: {self.worker_id}")
            logger.info(f"Capabilities: {self.capabilities}")
        except Exception as e:
            logger.error(f"Error registering worker: {str(e)}")
    
    async def shutdown_connectors(self):
        """Shutdown all connectors"""
        for job_type, connector in self.connectors.items():
            try:
                await connector.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down connector for {job_type}: {str(e)}")
    
    async def run(self):
        """Run the worker"""
        try:
            # Connect to Redis Hub
            logger.info(f"Connecting to Redis Hub at {self.redis_ws_url}")
            async with websockets.connect(self.redis_ws_url) as websocket:
                logger.info("Connected to Redis Hub")
                
                # Register worker
                await self.register_worker(websocket)
                
                # Start heartbeat task
                heartbeat_task = asyncio.create_task(self.send_heartbeat(websocket))
                
                # Process messages
                async for message in websocket:
                    await self.handle_message(websocket, message)
                
                # Cancel heartbeat task
                heartbeat_task.cancel()
        except Exception as e:
            logger.error(f"Error in worker: {str(e)}")
        finally:
            # Shutdown connectors
            await self.shutdown_connectors()
    
    def start(self):
        """Start the worker"""
        logger.info(f"Starting worker with ID: {self.worker_id}")
        asyncio.run(self.run())
