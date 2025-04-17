#!/usr/bin/env python3
# WebSocket connector base class for the EmProps Redis Worker
# Created: 2025-04-07T11:07:00-04:00

import os
import json
import asyncio
import aiohttp
import time
import sys
from typing import Dict, Any, Optional, Union, Callable

# Standard import approach - works in both Docker and local environments
# when the package structure is properly set up
# Updated: 2025-04-17T14:15:00-04:00 - Simplified import logic to avoid duplicate imports
try:
    # For when the module is imported as part of the worker package
    from worker.connector_interface import ConnectorInterface
except ImportError:
    try:
        # For when the module is imported directly or in Docker
        # where the worker directory is in the Python path
        from connector_interface import ConnectorInterface
    except ImportError:
        try:
            # Last resort - absolute imports
            from ..connector_interface import ConnectorInterface
        except ImportError:
            # If all else fails, define a minimal interface for type checking
            # This won't be used at runtime but helps with static analysis
            from abc import ABC, abstractmethod
            from typing import Dict, Any, Optional, Union, Callable
            
            class ConnectorInterface(ABC):
                """Minimal interface definition for type checking"""
                connector_name = None
                
                @abstractmethod
                async def initialize(self) -> bool: pass
                
                @abstractmethod
                def get_job_type(self) -> str: pass
                
                @abstractmethod
                def get_capabilities(self) -> Dict[str, Any]: pass
                
                @abstractmethod
                def get_connection_status(self) -> Dict[str, Any]: pass
                
                @abstractmethod
                def is_processing_job(self, job_id: str) -> bool: pass
                
                @abstractmethod
                async def process_job(self, websocket, job_id: str, payload: Dict[str, Any], send_progress_update) -> Dict[str, Any]: pass
                
                @abstractmethod
                async def shutdown(self) -> None: pass

# Import logger - this should be available in all environments
from core.utils.logger import logger

class WebSocketConnector(ConnectorInterface):
    """Base class for connectors that use WebSockets to communicate with external services"""
    
    # Base class is not directly usable by workers
    # Updated: 2025-04-07T15:50:00-04:00
    connector_name = None  # Set to None to indicate this is not directly usable
    
    # Version identifier to verify code deployment
    VERSION = "2025-04-17-14:35-handshake-error-fix"
    
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
        
        # Connection timeout settings
        # Updated: 2025-04-17T13:59:00-04:00 - Added connection timeout
        self.connection_timeout = float(os.environ.get("WORKER_CONNECTION_TIMEOUT", os.environ.get("CONNECTION_TIMEOUT", "30.0")))
        
        # Connection event handlers
        self.connection_event = asyncio.Event()
        self.connection_error = None
    
    async def connect(self) -> bool:
        """Connect to the WebSocket service with timeout
        
        Returns:
            bool: True if connection was successful, False otherwise
        """
        if not self.ws_url:
            logger.error(f"[connectors/websocket_connector.py connect()] WebSocket URL not set")
            return False
            
        logger.info(f"[connectors/websocket_connector.py connect()] Attempting to connect to {self.ws_url} (timeout: {self.connection_timeout}s)")
        self.connected = False
        self.connection_event.clear()
        self.connection_error = None

        try:
            # Prepare headers
            headers = self._get_connection_headers()
            
            # Close existing session if it exists
            if hasattr(self, 'session') and self.session:
                await self.session.close()

            # Create new session
            self.session = aiohttp.ClientSession()
            
            # Connect with timeout
            try:
                # Use asyncio.wait_for to implement connection timeout
                # Updated: 2025-04-17T14:35:00-04:00 - Removed protocols parameter to avoid handshake issues
                self.ws = await asyncio.wait_for(
                    self.session.ws_connect(
                        self.ws_url,
                        headers=headers,
                        heartbeat=30.0,  # Enable WebSocket protocol-level heartbeats
                        receive_timeout=60.0,  # Timeout for receiving messages
                        # Set up event handlers
                        # protocols=['websocket'],  # Removed to avoid handshake issues
                        autoclose=False,  # We'll handle closing ourselves
                        autoping=True     # Automatically respond to pings
                    ),
                    timeout=self.connection_timeout
                )
                
                # Set up event handlers for the WebSocket if available
                # Updated: 2025-04-17T14:16:00-04:00 - Added type checking to avoid attribute errors
                if hasattr(self.ws, 'on_close'):
                    self.ws.on_close = self._on_ws_close
                if hasattr(self.ws, 'on_error'):
                    self.ws.on_error = self._on_ws_error
                
                # Mark as connected and return success
                self.connected = True
                logger.info(f"[connectors/websocket_connector.py connect()] Successfully connected to WebSocket service")
                
                # Handle any service-specific connection steps
                await self._on_connect()
                
                return True
                
            except asyncio.TimeoutError:
                error_msg = f"Connection timed out after {self.connection_timeout} seconds"
                logger.error(f"[connectors/websocket_connector.py connect()] {error_msg}")
                self.connection_error = Exception(error_msg)
                return False
            except aiohttp.WSServerHandshakeError as e:
                # Updated: 2025-04-17T14:35:00-04:00 - Added specific handling for handshake errors
                error_msg = f"WebSocket handshake failed: {str(e)}"
                logger.error(f"[connectors/websocket_connector.py connect()] {error_msg}")
                # Store as connection_error and raise immediately to ensure job fails fast
                self.connection_error = e
                raise e  # Re-raise to ensure immediate failure
                
        except Exception as e:
            # Updated: 2025-04-17T14:36:00-04:00 - Improved error handling for connection failures
            error_msg = f"Error connecting to WebSocket service: {str(e)}"
            logger.error(f"[connectors/websocket_connector.py connect()] {error_msg}")
            self.connection_error = e
            
            # Check for specific error types that should cause immediate failure
            if isinstance(e, aiohttp.ClientConnectorError) or \
               isinstance(e, aiohttp.WSServerHandshakeError) or \
               "protocol" in str(e).lower():
                logger.error(f"[connectors/websocket_connector.py connect()] Critical connection error - raising to fail job immediately")
                raise e  # Re-raise to ensure immediate failure
            
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
        
    async def _on_ws_close(self, ws, code, message):
        """Handle WebSocket close event
        
        Args:
            ws: The WebSocket connection
            code: The close code
            message: The close message
        """
        # Updated: 2025-04-17T14:00:00-04:00 - Added WebSocket close handler
        logger.warning(f"[connectors/websocket_connector.py _on_ws_close] WebSocket connection closed: code={code}, message={message}")
        self.connected = False
        
        # Set connection error to trigger job failure
        self.connection_error = Exception(f"WebSocket connection closed: code={code}, message={message}")
        
        # Signal the connection event to unblock any waiting tasks
        self.connection_event.set()
        
    async def _on_ws_error(self, ws, error):
        """Handle WebSocket error event
        
        Args:
            ws: The WebSocket connection
            error: The error
        """
        # Updated: 2025-04-17T14:00:00-04:00 - Added WebSocket error handler
        logger.error(f"[connectors/websocket_connector.py _on_ws_error] WebSocket error: {str(error)}")
        
        # Set connection error to trigger job failure
        self.connection_error = error
        
        # Signal the connection event to unblock any waiting tasks
        self.connection_event.set()
    
    async def monitor_progress(self, job_id: str, send_progress_update: Callable) -> Dict[str, Any]:
        """Monitor job progress with heartbeat mechanism and connection monitoring
        
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
        connection_monitor_task = None
        
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
                        logger.warning(f"[connectors/websocket_connector.py send_heartbeats] Missed heartbeat #{missed_heartbeats}: WebSocket closed")
                    else:
                        # Send heartbeat through progress update
                        try:
                            # Include version in the message field for visibility in client
                            version_message = f"{self.get_job_type()} connection active [version: {self.VERSION}]"
                            await send_progress_update(job_id, -1, "heartbeat", version_message)
                            missed_heartbeats = 0  # Reset counter on successful heartbeat
                            logger.debug(f"[connectors/websocket_connector.py send_heartbeats] Sent heartbeat for job {job_id}")
                        except Exception as e:
                            missed_heartbeats += 1
                            logger.warning(f"[connectors/websocket_connector.py send_heartbeats] Missed heartbeat #{missed_heartbeats}: {str(e)}")
                    
                    # Check if we've missed too many heartbeats
                    if missed_heartbeats >= max_missed_heartbeats:
                        logger.error(f"[connectors/websocket_connector.py send_heartbeats] Missed {missed_heartbeats} heartbeats, connection considered failed")
                        raise Exception(f"WebSocket connection lost after {missed_heartbeats} missed heartbeats")
                    
                    # Wait for next heartbeat interval
                    await asyncio.sleep(heartbeat_interval)
            except asyncio.CancelledError:
                # Task was cancelled, this is normal during cleanup
                logger.debug(f"[connectors/websocket_connector.py send_heartbeats] Heartbeat task cancelled for job {job_id}")
            except Exception as e:
                # Propagate other exceptions
                logger.error(f"[connectors/websocket_connector.py send_heartbeats] Heartbeat error: {str(e)}")
                raise
        
        # Connection monitor function that checks for WebSocket events
        # Updated: 2025-04-17T14:01:00-04:00 - Added connection monitor
        async def monitor_connection():
            try:
                while True:
                    # Check if we have a connection error
                    if self.connection_error is not None:
                        logger.error(f"[connectors/websocket_connector.py monitor_connection] Connection error detected: {str(self.connection_error)}")
                        raise self.connection_error
                    
                    # Check if the WebSocket is closed
                    if self.ws is None or self.ws.closed:
                        logger.error(f"[connectors/websocket_connector.py monitor_connection] WebSocket connection is closed")
                        raise Exception("WebSocket connection is closed")
                    
                    # Wait a short time before checking again
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                # Task was cancelled, this is normal during cleanup
                logger.debug(f"[connectors/websocket_connector.py monitor_connection] Connection monitor task cancelled for job {job_id}")
            except Exception as e:
                # Propagate other exceptions
                logger.error(f"[connectors/websocket_connector.py monitor_connection] Connection monitor error: {str(e)}")
                raise
        
        try:
            # Start heartbeat task
            heartbeat_task = asyncio.create_task(send_heartbeats())
            
            # Start connection monitor task
            # Updated: 2025-04-17T14:01:00-04:00 - Added connection monitor task
            connection_monitor_task = asyncio.create_task(monitor_connection())
            
            # Send initial progress update
            await send_progress_update(job_id, 0, "started", f"Starting {self.get_job_type()} job")
            
            # Call the service-specific monitoring implementation
            final_result = await self._monitor_service_progress(job_id, send_progress_update)
            
            # Send completion update
            await send_progress_update(job_id, 100, "completed", "Job completed successfully")
            
            return final_result
        except Exception as e:
            logger.error(f"[connectors/websocket_connector.py monitor_progress] Error: {str(e)}")
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
                    logger.error(f"[connectors/websocket_connector.py monitor_progress] Error cancelling heartbeat task: {str(e)}")
            
            # Always cancel the connection monitor task if it exists
            # Updated: 2025-04-17T14:01:00-04:00 - Added connection monitor task cleanup
            if connection_monitor_task and not connection_monitor_task.done():
                connection_monitor_task.cancel()
                try:
                    await connection_monitor_task
                except asyncio.CancelledError:
                    pass  # This is expected
                except Exception as e:
                    logger.error(f"[connectors/websocket_connector.py monitor_progress] Error cancelling connection monitor task: {str(e)}")
    
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
            logger.info(f"[connectors/websocket_connector.py process_job] Starting job {job_id} for {self.get_job_type()} service")
            
            # Reset connection error before starting
            # Updated: 2025-04-17T14:02:00-04:00 - Reset connection error before starting
            self.connection_error = None
            
            # Connect to the WebSocket service if not already connected
            # Updated: 2025-04-17T14:36:00-04:00 - Improved connection error handling
            if not self.connected:
                logger.info(f"[connectors/websocket_connector.py process_job] Connecting to {self.get_job_type()} service with timeout {self.connection_timeout}s")
                try:
                    connected = await self.connect()
                    if not connected:
                        error_msg = f"Failed to connect to {self.get_job_type()} service"
                        if self.connection_error:
                            error_msg += f": {str(self.connection_error)}"
                        raise Exception(error_msg)
                except Exception as e:
                    # Catch and report any connection errors
                    logger.error(f"[connectors/websocket_connector.py process_job] Connection error: {str(e)}")
                    await send_progress_update(job_id, 0, "error", f"Connection error: {str(e)}")
                    return {
                        "status": "failed",
                        "error": f"Connection error: {str(e)}"
                    }
            
            # Check if connection was lost during preparation
            if self.connection_error is not None:
                error_msg = f"Connection error detected: {str(self.connection_error)}"
                logger.error(f"[connectors/websocket_connector.py process_job] {error_msg}")
                await send_progress_update(job_id, 0, "error", error_msg)
                return {
                    "status": "failed",
                    "error": error_msg
                }
            
            # Prepare the job for processing
            await self._prepare_job(job_id, payload)
            
            # Check again if connection was lost during preparation
            if self.connection_error is not None:
                error_msg = f"Connection lost during preparation: {str(self.connection_error)}"
                logger.error(f"[connectors/websocket_connector.py process_job] {error_msg}")
                await send_progress_update(job_id, 0, "error", error_msg)
                return {
                    "status": "failed",
                    "error": error_msg
                }
            
            # Process the job using service-specific implementation
            # AI-generated fix: 2025-04-04T20:13:55 - Added call to _process_service_job before monitoring progress
            # Updated: 2025-04-17T14:02:00-04:00 - Added connection error checks
            # Updated: 2025-04-17T14:36:00-04:00 - Improved error handling
            logger.info(f"[connectors/websocket_connector.py process_job] Calling service-specific job processing for {job_id}")
            result = await self._process_service_job(websocket, job_id, payload, send_progress_update)
            
            # Return the result
            return result
        except Exception as e:
            logger.error(f"[connectors/websocket_connector.py process_job] Error processing job {job_id}: {str(e)}")
            raise
        finally:
            # Clear current job ID when done
            logger.info(f"[connectors/websocket_connector.py process_job] Completed job {job_id} for {self.get_job_type()} service")
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
            
            # Reset connection event and error
            # Updated: 2025-04-17T14:03:00-04:00 - Reset connection event and error
            self.connection_event.clear()
            self.connection_error = None
            
        except Exception as e:
            logger.error(f"[connectors/websocket_connector.py _disconnect] Error disconnecting: {str(e)}")
    
    async def shutdown(self) -> None:
        """Clean up resources when worker is shutting down"""
        logger.info(f"[connectors/websocket_connector.py shutdown] Shutting down {self.get_job_type()} connector")
        await self._disconnect()
        logger.info(f"[connectors/websocket_connector.py shutdown] {self.get_job_type()} connector shut down")
    
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
            "version": self.VERSION,  # Include version to verify code deployment
            "connection_timeout": self.connection_timeout  # Added: 2025-04-17T14:03:00-04:00
        }
        
        # Add connection error if present
        # Updated: 2025-04-17T14:03:00-04:00 - Added connection error to status
        if self.connection_error is not None:
            result["connection_error"] = str(self.connection_error)
            
        return result
        
    def is_processing_job(self, job_id: str) -> bool:
        """Check if this connector is currently processing the specified job
        
        Args:
            job_id (str): The ID of the job to check
            
        Returns:
            bool: True if this connector is processing the job, False otherwise
        """
        return self.current_job_id == job_id
