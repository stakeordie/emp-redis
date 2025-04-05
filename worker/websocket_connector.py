#!/usr/bin/env python3
# WebSocket connector base class for the EmProps Redis Worker
import os
import json
import asyncio
import aiohttp
import time
from typing import Dict, Any, Optional, Union, Callable

# Try direct imports first (for Docker container)
try:
    from connector_interface import ConnectorInterface
except ImportError:
    # Fall back to package imports (for local development)
    from worker.connector_interface import ConnectorInterface
from core.utils.logger import logger

class WebSocketConnector(ConnectorInterface):
    """Base class for connectors that use WebSockets to communicate with external services"""
    
    # Version identifier to verify code deployment
    VERSION = "2025-04-04-19:36-connector-details-update"
    
    def __init__(self):
        """Initialize the WebSocket connector base class"""
        super().__init__()
        
        # WebSocket connection settings
        self.ws_url = None
        self.ws = None
        self.session = None
        self.connected = False
        self.connection_details = {}
        
        # Authentication settings
        self.username = None
        self.password = None
        self.auth_token = None
        self.use_ssl = False
        
        # Job tracking
        self.current_job_id = None
    
    async def connect(self) -> bool:
        """Connect to the WebSocket service
        
        Returns:
            bool: True if connection was successful, False otherwise
        """
        if not self.ws_url:
            logger.error(f"[websocket_connector.py connect()] WebSocket URL not set")
            return False
            
        logger.info(f"[websocket_connector.py connect()] Attempting to connect to {self.ws_url}")
        self.connected = False

        try:
            # Prepare headers
            headers = self._get_connection_headers()
            
            # Close existing session if it exists
            if hasattr(self, 'session') and self.session:
                await self.session.close()

            # Create new session and connect
            self.session = aiohttp.ClientSession()
            self.ws = await self.session.ws_connect(
                self.ws_url,
                headers=headers
            )
            
            # Mark as connected and return success
            self.connected = True
            logger.info(f"[websocket_connector.py connect()] Successfully connected to WebSocket service")
            
            # Handle any service-specific connection steps
            await self._on_connect()
            
            return True
        except Exception as e:
            logger.error(f"[websocket_connector.py connect()] Error connecting to WebSocket service: {str(e)}")
            return False
    
    def _get_connection_headers(self) -> Dict[str, str]:
        """Get headers for WebSocket connection
        
        Override this method in subclasses to provide custom headers
        
        Returns:
            Dict[str, str]: Headers for WebSocket connection
        """
        headers = {
            "Upgrade": "websocket",
            "Connection": "Upgrade",
            "Sec-WebSocket-Version": "13"
        }
        
        # Add authentication if provided
        if self.username and self.password:
            import base64
            credentials = f"{self.username}:{self.password}"
            encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
            headers["Authorization"] = f"Basic {encoded_credentials}"
        elif self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
            
        return headers
    
    async def _on_connect(self) -> None:
        """Handle service-specific connection steps
        
        Override this method in subclasses to handle service-specific connection steps
        """
        pass
    
    async def _on_disconnect(self) -> None:
        """Handle service-specific disconnection steps
        
        Override this method in subclasses to handle service-specific disconnection steps
        """
        pass
    
    async def monitor_progress(self, job_id: str, send_progress_update: Callable) -> Dict[str, Any]:
        """Monitor job progress with heartbeat mechanism
        
        Args:
            job_id (str): The ID of the current job
            send_progress_update (Callable): Function to send progress updates
        
        Returns:
            Dict[str, Any]: Final job result or error details
        """
        if not self.connected or self.ws is None:
            raise Exception("Not connected to WebSocket service")
        
        final_result = None
        job_completed = False
        heartbeat_task = None
        
        # Heartbeat function that runs as a separate task
        async def send_heartbeats():
            missed_heartbeats = 0
            max_missed_heartbeats = 4  # Error after 4 missed heartbeats (20 seconds)
            heartbeat_interval = 5  # 5 seconds between heartbeats
            
            try:
                while True:
                    # Check if websocket is still connected
                    if self.ws is None or self.ws.closed:
                        missed_heartbeats += 1
                        logger.warning(f"[websocket_connector.py send_heartbeats] Missed heartbeat #{missed_heartbeats}: WebSocket closed")
                    else:
                        # Send heartbeat through progress update
                        try:
                            # Include version in the message field for visibility in client
                            version_message = f"{self.get_job_type()} connection active [version: {self.VERSION}]"
                            await send_progress_update(job_id, -1, "heartbeat", version_message)
                            missed_heartbeats = 0  # Reset counter on successful heartbeat
                            logger.debug(f"[websocket_connector.py send_heartbeats] Sent heartbeat for job {job_id}")
                        except Exception as e:
                            missed_heartbeats += 1
                            logger.warning(f"[websocket_connector.py send_heartbeats] Missed heartbeat #{missed_heartbeats}: {str(e)}")
                    
                    # Check if we've missed too many heartbeats
                    if missed_heartbeats >= max_missed_heartbeats:
                        logger.error(f"[websocket_connector.py send_heartbeats] Missed {missed_heartbeats} heartbeats, connection considered failed")
                        raise Exception(f"WebSocket connection lost after {missed_heartbeats} missed heartbeats")
                    
                    # Wait for next heartbeat interval
                    await asyncio.sleep(heartbeat_interval)
            except asyncio.CancelledError:
                # Task was cancelled, this is normal during cleanup
                logger.debug(f"[websocket_connector.py send_heartbeats] Heartbeat task cancelled for job {job_id}")
            except Exception as e:
                # Propagate other exceptions
                logger.error(f"[websocket_connector.py send_heartbeats] Heartbeat error: {str(e)}")
                raise
        
        try:
            # Start heartbeat task
            heartbeat_task = asyncio.create_task(send_heartbeats())
            
            # Send initial progress update
            await send_progress_update(job_id, 0, "started", f"Starting {self.get_job_type()} job")
            
            # Call the service-specific monitoring implementation
            final_result = await self._monitor_service_progress(job_id, send_progress_update)
            
            # Send completion update
            await send_progress_update(job_id, 100, "completed", "Job completed successfully")
            
            return final_result
        except Exception as e:
            logger.error(f"[websocket_connector.py monitor_progress] Error: {str(e)}")
            await send_progress_update(job_id, 0, "error", str(e))
            raise
        finally:
            # Always cancel the heartbeat task if it exists
            if heartbeat_task and not heartbeat_task.done():
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass  # This is expected
                except Exception as e:
                    logger.error(f"[websocket_connector.py monitor_progress] Error cancelling heartbeat task: {str(e)}")
    
    async def _monitor_service_progress(self, job_id: str, send_progress_update: Callable) -> Dict[str, Any]:
        """Service-specific implementation of progress monitoring
        
        Override this method in subclasses to implement service-specific progress monitoring
        
        Args:
            job_id (str): The ID of the current job
            send_progress_update (Callable): Function to send progress updates
            
        Returns:
            Dict[str, Any]: Final job result
        """
        raise NotImplementedError("Subclasses must implement _monitor_service_progress")
    
    async def process_job(self, websocket, job_id: str, payload: Dict[str, Any], send_progress_update) -> Dict[str, Any]:
        """Process a job using the WebSocket service
        
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
            logger.info(f"[websocket_connector.py process_job] Starting job {job_id} for {self.get_job_type()} service")
            
            # Connect to the WebSocket service if not already connected
            if not self.connected:
                connected = await self.connect()
                if not connected:
                    raise Exception(f"Failed to connect to {self.get_job_type()} service")
            
            # Prepare the job for processing
            await self._prepare_job(job_id, payload)
            
            # Process the job using service-specific implementation
            # AI-generated fix: 2025-04-04T20:13:55 - Added call to _process_service_job before monitoring progress
            logger.info(f"[websocket_connector.py process_job] Calling service-specific job processing for {job_id}")
            result = await self._process_service_job(websocket, job_id, payload, send_progress_update)
            
            # Return the result
            return result
        except Exception as e:
            logger.error(f"[websocket_connector.py process_job] Error processing job {job_id}: {str(e)}")
            raise
        finally:
            # Clear current job ID when done
            logger.info(f"[websocket_connector.py process_job] Completed job {job_id} for {self.get_job_type()} service")
            self.current_job_id = None
    
    async def _prepare_job(self, job_id: str, payload: Dict[str, Any]) -> None:
        """Prepare the job for processing
        
        This method is a placeholder and should be implemented in subclasses
        
        Args:
            job_id (str): The ID of the job to prepare
            payload (Dict[str, Any]): The job payload
        """
        # This is a placeholder method that should be overridden by subclasses
        pass
    
    async def _process_service_job(self, websocket, job_id: str, payload: Dict[str, Any], send_progress_update) -> Dict[str, Any]:
        """Service-specific implementation of job processing
        
        Override this method in subclasses to implement service-specific job processing
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
            job_id: The ID of the job to process
            payload: The job payload
            send_progress_update: Function to send progress updates
            
        Returns:
            Dict[str, Any]: Job result
        """
        raise NotImplementedError("Subclasses must implement _process_service_job")
    
    async def _disconnect(self) -> None:
        """Disconnect from the WebSocket service"""
        try:
            # Call service-specific disconnect handler
            await self._on_disconnect()
            
            # Close WebSocket connection
            if self.ws is not None:
                await self.ws.close()
                self.ws = None
            
            # Close session
            if self.session is not None:
                await self.session.close()
                self.session = None
                
            self.connected = False
        except Exception as e:
            logger.error(f"[websocket_connector.py _disconnect] Error disconnecting: {str(e)}")
    
    async def shutdown(self) -> None:
        """Clean up resources when worker is shutting down"""
        logger.info(f"[websocket_connector.py shutdown] Shutting down {self.get_job_type()} connector")
        await self._disconnect()
        logger.info(f"[websocket_connector.py shutdown] {self.get_job_type()} connector shut down")
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get the current connection status of the connector
        
        Returns:
            Dict[str, Any]: Connection status information
        """
        # Explicitly create and return a Dict[str, Any] to satisfy type checking
        result: Dict[str, Any] = {
            "connected": self.connected,
            "service": self.get_job_type(),
            "details": self.connection_details,
            "ws_url": self.ws_url,
            "use_ssl": self.use_ssl,
            "current_job_id": self.current_job_id,
            "version": self.VERSION  # Include version to verify code deployment
        }
        return result
        
    def is_processing_job(self, job_id: str) -> bool:
        """Check if this connector is currently processing the specified job
        
        Args:
            job_id (str): The ID of the job to check
            
        Returns:
            bool: True if this connector is processing the job, False otherwise
        """
        return self.current_job_id == job_id
