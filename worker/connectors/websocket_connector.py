#!/usr/bin/env python3
# WebSocket connector base class for the EmProps Redis Worker
# Created: 2025-04-07T11:07:00-04:00

import os
import json
import asyncio
import aiohttp
import logging
import time
from typing import Dict, Any, Optional, Callable, List, Tuple

# [2025-05-23T09:50:00-04:00] Added standardized message size configuration
# Define consistent size limits as environment variables with defaults
MAX_WS_MESSAGE_SIZE_MB = int(os.environ.get('MAX_WS_MESSAGE_SIZE_MB', 100))  # 100MB default
MAX_WS_MESSAGE_SIZE_BYTES = MAX_WS_MESSAGE_SIZE_MB * 1024 * 1024

# Standard import approach - works in both Docker and local environments
# when the package structure is properly set up
# Updated: 2025-04-17T14:15:00-04:00 - Simplified import logic to avoid duplicate imports
# [2025-05-25T16:50:00-04:00] Simplified import structure to avoid redefinition errors
# Import the ConnectorInterface directly from the most likely location
from worker.connector_interface import ConnectorInterface

# If the import fails at runtime, we'll get an ImportError, but this is better than
# having multiple definitions of ConnectorInterface which causes type errors

# Import logger - this should be available in all environments
from core.utils.logger import logger

class WebSocketConnector(ConnectorInterface):
    """Base class for connectors that use WebSockets to communicate with external services"""
    
    # [2025-05-25T21:30:00-04:00] Implemented connector_id property to replace connector_name
    # This base class is not directly usable by workers
    @property
    def connector_id(self) -> str:
        """Get the connector identifier used for loading and identification
        
        Returns:
            str: The connector identifier string
            
        Raises:
            NotImplementedError: This base class should not be used directly
        """
        # Base class is not directly usable
        raise NotImplementedError("WebSocketConnector is a base class and should not be used directly")
    
    # Version identifier to verify code deployment
    VERSION = "2025-04-17-15:05-error-handling-fix"
    
    def __init__(self):
        """Initialize the WebSocket connector base class"""
        super().__init__()
        
        # WebSocket connection settings
        self.ws_url = None
        self.ws = None
        self.session = None
        self.connected = False
        self.connection_error = None
        self.current_job_id = None
        
        # Connection monitoring
        self.last_message_received_time = None
        self.last_message_sent_time = None
        self.connection_start_time = None
        self.message_count = 0
        self.error_count = 0
        
        # Default timeout values
        self.connection_timeout = float(os.environ.get('WORKER_CONNECTION_TIMEOUT', 30.0))
        
        # Authentication settings
        self.username = None
        self.password = None
        self.auth_token = None
        self.use_ssl = False
        
        # Job tracking
        self.current_job_id = None
        
        # Connection event handlers
        self.connection_event = asyncio.Event()
        self.connection_error = None
        
        # Diagnostic tracking
        self.connection_attempts = 0
        self.last_connection_attempt_time = None
    
    async def connect(self) -> bool:
        """Connect to the WebSocket service
        
        Returns:
            bool: True if connected successfully
            
        Raises:
            Exception: If connection fails for any reason
        """
        # 2025-04-25-17:55 - Updated to use a much shorter timeout (5 seconds) for initial connection
        # This ensures we fail fast if the connection can't be established
        connection_timeout = 5.0  # Use a fixed 5-second timeout for initial connection
        
        try:
            # Record connection attempt
            self.connection_attempts += 1
            self.last_connection_attempt_time = time.time()
            self.connection_start_time = time.time()
            
            # 2025-04-25-18:02 - Added eye-catching log entries for connection attempts
            logger.debug(f"""[connectors/websocket_connector.py connect()] 
╔══════════════════════════════════════════════════════════════════════════════╗
║ WEBSOCKET CONNECTION ATTEMPT #{self.connection_attempts}                                  ║
║ URL: {self.ws_url}                                                           ║
║ Timeout: {connection_timeout}s                                               ║
║ Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.connection_start_time))}   ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
            
            # Create a new aiohttp session if needed
            if self.session is None or self.session.closed:
                # Configure timeout settings
                timeout = aiohttp.ClientTimeout(
                    total=None,  # No total timeout
                    connect=connection_timeout,
                    sock_connect=connection_timeout,
                    sock_read=60.0  # Default read timeout
                )
                self.session = aiohttp.ClientSession(timeout=timeout)
                logger.debug(f"[connectors/websocket_connector.py connect()] WEBSOCKET_STATUS: Created new aiohttp session with timeout settings: connect={connection_timeout}s, sock_connect={connection_timeout}s, sock_read=60.0s")
            
            # Get connection URL and headers
            self.ws_url = self._get_connection_url()
            headers = self._get_connection_headers()
            
            # Log connection parameters
            logger.debug(f"[connectors/websocket_connector.py connect()] WEBSOCKET_STATUS: Connection URL: {self.ws_url}")
            logger.debug(f"[connectors/websocket_connector.py connect()] WEBSOCKET_STATUS: Connection headers: {headers}")
            
            # Connect with timeout
            try:
                logger.debug(f"[connectors/websocket_connector.py connect()] WEBSOCKET_STATUS: Starting WebSocket connection with params: heartbeat=30.0, receive_timeout=60.0, autoclose=False, autoping=True")
                
                connection_start = time.time()
                # [2025-05-23T09:50:15-04:00] Added max_msg_size parameter to increase message size limit
                logger.debug(f"[2025-05-23T09:50:15-04:00] Using WebSocket message size limit: {MAX_WS_MESSAGE_SIZE_MB}MB ({MAX_WS_MESSAGE_SIZE_BYTES} bytes)")
                
                self.ws = await asyncio.wait_for(
                    self.session.ws_connect(
                        self.ws_url,
                        headers=headers,
                        heartbeat=30.0,  # Enable WebSocket protocol-level heartbeats
                        receive_timeout=60.0,  # Timeout for receiving messages
                        # Do not specify protocols to avoid handshake issues
                        autoclose=False,  # We'll handle closing ourselves
                        autoping=True,    # Automatically respond to pings
                        max_msg_size=MAX_WS_MESSAGE_SIZE_BYTES  # Use standardized message size limit
                    ),
                    timeout=connection_timeout
                )
                
                connection_time = time.time() - connection_start
                logger.debug(f"[connectors/websocket_connector.py connect()] WEBSOCKET_STATUS: Connection established in {connection_time:.2f} seconds")
                logger.debug(f"[connectors/websocket_connector.py connect()] WEBSOCKET_STATUS: WebSocket connection details: {self.ws}")
                
                # Set up event handlers for the WebSocket if available
                # [2025-05-25T16:55:00-04:00] Added null check for self.ws to prevent type errors
                if self.ws is not None:
                    if hasattr(self.ws, 'on_close'):
                        logger.debug(f"[connectors/websocket_connector.py connect()] WEBSOCKET_STATUS: Setting up on_close event handler")
                        self.ws.on_close = self._on_ws_close
                    else:
                        logger.warning(f"[connectors/websocket_connector.py connect()] WEBSOCKET_STATUS: WebSocket does not support on_close event handler")
                        
                    if hasattr(self.ws, 'on_error'):
                        logger.debug(f"[connectors/websocket_connector.py connect()] WEBSOCKET_STATUS: Setting up on_error event handler")
                        self.ws.on_error = self._on_ws_error
                    else:
                        logger.warning(f"[connectors/websocket_connector.py connect()] WEBSOCKET_STATUS: WebSocket does not support on_error event handler")
                else:
                    logger.warning(f"[connectors/websocket_connector.py connect()] WEBSOCKET_STATUS: Cannot set event handlers: WebSocket connection is None")
                
                # Mark as connected and return success
                self.connected = True
                self.last_message_received_time = time.time()
                self.last_message_sent_time = time.time()
                # 2025-04-25-18:02 - Added eye-catching log entry for successful connection
                logger.debug(f"""[connectors/websocket_connector.py connect()] 
╔══════════════════════════════════════════════════════════════════════════════╗
║ WEBSOCKET CONNECTION SUCCESS!!! ✓✓✓                                          ║
║ URL: {self.ws_url}                                                           ║
║ Connected in: {time.time() - self.connection_start_time:.2f}s                ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
                
                # Handle any service-specific connection steps
                logger.debug(f"[connectors/websocket_connector.py connect()] WEBSOCKET_STATUS: Calling service-specific _on_connect() handler")
                await self._on_connect()
                
                return True
                
            except asyncio.TimeoutError as e:
                error_msg = f"Connection timed out after {connection_timeout} seconds"
                # 2025-04-25-18:02 - Added eye-catching log entry for connection timeout
                logger.error(f"""[connectors/websocket_connector.py connect()] 
╔══════════════════════════════════════════════════════════════════════════════╗
║ WEBSOCKET CONNECTION FAILED!!! ✗✗✗                                          ║
║ URL: {self.ws_url}                                                           ║
║ Error: CONNECTION TIMEOUT after {connection_timeout}s                         ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
                self.connection_error = Exception(error_msg)
                # 2025-04-25-17:40 - Always raise exceptions for connection failures
                raise Exception(error_msg) from e
                
            except aiohttp.WSServerHandshakeError as e:
                error_msg = f"WebSocket handshake failed: {str(e)}"
                logger.error(f"[connectors/websocket_connector.py connect()] WEBSOCKET_STATUS: {error_msg}")
                logger.error(f"[connectors/websocket_connector.py connect()] WEBSOCKET_STATUS: This may indicate a protocol mismatch or server configuration issue")
                # Store as connection_error and raise immediately to ensure job fails fast
                self.connection_error = e
                raise e  # Re-raise to ensure immediate failure
                
        except Exception as e:
            error_type = type(e).__name__
            error_msg = f"Error connecting to WebSocket service: {error_type} - {str(e)}"
            # 2025-04-25-18:02 - Added eye-catching log entry for connection errors
            logger.error(f"""[connectors/websocket_connector.py connect()] 
╔══════════════════════════════════════════════════════════════════════════════╗
║ WEBSOCKET CONNECTION FAILED!!! ✗✗✗                                          ║
║ URL: {self.ws_url}                                                           ║
║ Error Type: {error_type}                                                     ║
║ Error: {str(e)}                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
            self.connection_error = e
            
            # 2025-04-25-17:40 - Always raise exceptions for connection failures
            # No more returning False, all connection errors should raise exceptions
            raise
    
    async def send_message(self, message: Dict[str, Any]) -> bool:
        """Send a message to the WebSocket service
        
        Args:
            message: The message to send
            
        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not self.connected or self.ws is None:
            logger.error(f"[connectors/websocket_connector.py send_message] WEBSOCKET_STATUS: Cannot send message: not connected")
            return False
            
        try:
            # Log message details (excluding potentially large payloads)
            message_type = message.get('type', 'unknown')
            message_id = message.get('id', 'no-id')
            log_message = f"Sending message type={message_type}, id={message_id}"
            
            if 'data' in message and isinstance(message['data'], dict):
                # Include some data fields but not large ones
                safe_data = {k: v for k, v in message['data'].items() 
                             if k != 'prompt' and not isinstance(v, (dict, list)) 
                             or (isinstance(v, (dict, list)) and len(str(v)) < 100)}
                log_message += f", data={safe_data}"
            
            logger.debug(f"[connectors/websocket_connector.py send_message] WEBSOCKET_STATUS: {log_message}")
            
            # Send the message and update tracking
            send_start = time.time()
            await self.ws.send_json(message)
            send_time = time.time() - send_start
            
            self.last_message_sent_time = time.time()
            self.message_count += 1
            
            logger.debug(f"[connectors/websocket_connector.py send_message] WEBSOCKET_STATUS: Message sent successfully in {send_time:.4f}s")
            return True
            
        except Exception as e:
            error_type = type(e).__name__
            logger.error(f"[connectors/websocket_connector.py send_message] WEBSOCKET_STATUS: Error sending message: {error_type} - {str(e)}")
            self.connection_error = e
            self.connected = False
            self.error_count += 1
            return False
    
    def _get_connection_url(self) -> str:
        """Get the WebSocket connection URL
        
        Override this method in subclasses to provide service-specific URL generation.
        Base implementation returns self.ws_url if it's already set, otherwise raises an error.
        
        Returns:
            str: The WebSocket connection URL
        
        Raises:
            ValueError: If ws_url is not set and method is not overridden by subclass
        """
        # 2025-04-17-19:48 - Added default implementation of _get_connection_url method
        # [2025-05-25T16:55:00-04:00] Fixed return type to ensure it always returns a string
        if hasattr(self, 'ws_url') and self.ws_url is not None:
            # Ensure we return a string to match the declared return type
            return str(self.ws_url)
        else:
            raise ValueError("WebSocket URL not set. Either set self.ws_url directly or override _get_connection_url() in subclass.")
    
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
        
    async def _on_ws_close(self, *args, **kwargs):
        """Handle WebSocket close event"""
        close_code = args[0] if args else "unknown"
        close_reason = kwargs.get('message', 'No reason provided')
        connection_duration = time.time() - (self.connection_start_time or time.time())
        
        logger.warning(f"[connectors/websocket_connector.py _on_ws_close] WEBSOCKET_STATUS: Connection CLOSED after {connection_duration:.2f}s - Code: {close_code}, Reason: {close_reason}")
        logger.debug(f"[connectors/websocket_connector.py _on_ws_close] WEBSOCKET_STATUS: Full close details - args: {args}, kwargs: {kwargs}")
        
        self.connected = False
        self.connection_error = Exception(f"WebSocket connection closed: Code {close_code} - {close_reason}")
        
    async def _on_ws_error(self, *args, **kwargs):
        """Handle WebSocket error event"""
        error_type = type(args[0]).__name__ if args and isinstance(args[0], Exception) else "unknown"
        error_msg = str(args[0]) if args else "No error details"
        connection_duration = time.time() - (self.connection_start_time or time.time())
        
        logger.error(f"[connectors/websocket_connector.py _on_ws_error] WEBSOCKET_STATUS: Connection ERROR after {connection_duration:.2f}s - Type: {error_type}, Message: {error_msg}")
        logger.debug(f"[connectors/websocket_connector.py _on_ws_error] WEBSOCKET_STATUS: Full error details - args: {args}, kwargs: {kwargs}")
        
        self.error_count += 1
        self.connected = False
        self.connection_error = Exception(f"WebSocket connection error: {error_type} - {error_msg}")
    
    async def monitor_progress(self, job_id: str, send_progress_update: Callable) -> Dict[str, Any]:
        # Log monitoring start with connection details
        logger.debug(f"[connectors/websocket_connector.py monitor_progress] WEBSOCKET_STATUS: Starting progress monitoring for job {job_id}")
        logger.debug(f"[connectors/websocket_connector.py monitor_progress] WEBSOCKET_STATUS: Connection state: connected={self.connected}, last_message_received={self.last_message_received_time}, last_message_sent={self.last_message_sent_time}")
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
            logger.debug(f"[connectors/websocket_connector.py monitor_progress] WEBSOCKET_STATUS: Starting heartbeat task")
            heartbeat_task = asyncio.create_task(send_heartbeats())
            
            # Start connection monitor task
            logger.debug(f"[connectors/websocket_connector.py monitor_progress] WEBSOCKET_STATUS: Starting connection monitor task")
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
        logger.debug(f"[connectors/websocket_connector.py _monitor_service_progress] WEBSOCKET_STATUS: Base class implementation called - subclass should override")
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
            logger.debug(f"[connectors/websocket_connector.py process_job] Starting job {job_id} for {self.get_job_type()} service")
            
            # Reset connection error before starting
            self.connection_error = None
            
            # Connect to the WebSocket service if not already connected
            if not self.connected:
                logger.debug(f"[connectors/websocket_connector.py process_job] Connecting to {self.get_job_type()} service with timeout {self.connection_timeout}s")
                try:
                    # 2025-04-25-17:45 - connect() now always raises exceptions on failure
                    await self.connect()
                    # If we get here, connection was successful
                    logger.debug(f"[connectors/websocket_connector.py process_job] Successfully connected to {self.get_job_type()} service")
                except Exception as e:
                    # Catch and report any connection errors
                    error_type = type(e).__name__
                    error_msg = f"Connection error: {error_type} - {str(e)}"
                    logger.error(f"[connectors/websocket_connector.py process_job] {error_msg}")
                    await send_progress_update(job_id, 0, "error", error_msg)
                    
                    # Return failure status immediately
                    return {
                        "status": "failed",
                        "error": error_msg
                    }
            
            # Double-check connection state
            if not self.connected or self.ws is None or (hasattr(self.ws, 'closed') and self.ws.closed):
                error_msg = "WebSocket connection is not established or was closed"
                logger.error(f"[connectors/websocket_connector.py process_job] {error_msg}")
                await send_progress_update(job_id, 0, "error", error_msg)
                
                # Return failure status
                return {
                    "status": "failed",
                    "error": error_msg
                }
            
            # Check if connection was lost during preparation
            if self.connection_error is not None:
                error_msg = f"Connection error detected: {str(self.connection_error)}"
                logger.error(f"[connectors/websocket_connector.py process_job] {error_msg}")
                await send_progress_update(job_id, 0, "error", error_msg)
                
                # Return failure status
                return {
                    "status": "failed",
                    "error": error_msg
                }
            
            # Prepare the job for processing
            try:
                await self._prepare_job(job_id, payload)
            except Exception as e:
                # Catch and report any preparation errors
                error_type = type(e).__name__
                error_msg = f"Job preparation error: {error_type} - {str(e)}"
                logger.error(f"[connectors/websocket_connector.py process_job] {error_msg}")
                await send_progress_update(job_id, 0, "error", error_msg)
                
                # Return failure status
                return {
                    "status": "failed",
                    "error": error_msg
                }
            
            # Check again if connection was lost during preparation
            if self.connection_error is not None:
                error_msg = f"Connection lost during preparation: {str(self.connection_error)}"
                logger.error(f"[connectors/websocket_connector.py process_job] {error_msg}")
                await send_progress_update(job_id, 0, "error", error_msg)
                
                # Return failure status
                return {
                    "status": "failed",
                    "error": error_msg
                }
            
            # Process the job using service-specific implementation
            logger.debug(f"[connectors/websocket_connector.py process_job] Calling service-specific job processing for {job_id}")
            try:
                result = await self._process_service_job(websocket, job_id, payload, send_progress_update)
                
                # Validate result to ensure it has a status
                if not isinstance(result, dict):
                    logger.warning(f"[connectors/websocket_connector.py process_job] Result is not a dictionary: {result}")
                    result = {"status": "completed", "data": result}
                
                # Ensure result has a status field
                if "status" not in result:
                    result["status"] = "completed"
                    
                # Log the final result status
                logger.debug(f"[connectors/websocket_connector.py process_job] Completed job {job_id} with status: {result.get('status')}")
                
                # Return the result
                return result
                
            except Exception as e:
                # Catch and report any processing errors
                error_type = type(e).__name__
                error_msg = f"Job processing error: {error_type} - {str(e)}"
                logger.error(f"[connectors/websocket_connector.py process_job] {error_msg}")
                await send_progress_update(job_id, 0, "error", error_msg)
                
                # Return failure status
                return {
                    "status": "failed",
                    "error": error_msg
                }
        except Exception as e:
            # Catch-all for any unexpected errors
            error_type = type(e).__name__
            error_msg = f"Unexpected error: {error_type} - {str(e)}"
            logger.error(f"[connectors/websocket_connector.py process_job] {error_msg}")
            
            try:
                await send_progress_update(job_id, 0, "error", error_msg)
            except Exception as send_error:
                logger.error(f"[connectors/websocket_connector.py process_job] Failed to send error update: {str(send_error)}")
            
            # Return failure status
            return {
                "status": "failed",
                "error": error_msg
            }
        finally:
            # Clear current job ID when done
            logger.debug(f"[connectors/websocket_connector.py process_job] Completed job {job_id} for {self.get_job_type()} service")
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
            Dict[str, Any]: Job result with status field ("completed" or "failed")
        """
        # Updated: 2025-04-17T15:05:00-04:00 - Added note about required status field
        logger.error(f"[connectors/websocket_connector.py _process_service_job] Subclass must implement this method")
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
            self.connection_event.clear()
            self.connection_error = None
            
        except Exception as e:
            logger.error(f"[connectors/websocket_connector.py _disconnect] Error disconnecting: {str(e)}")
    
    async def shutdown(self) -> None:
        """Clean up resources when worker is shutting down"""
        logger.debug(f"[connectors/websocket_connector.py shutdown] Shutting down {self.get_job_type()} connector")
        await self._disconnect()
        logger.debug(f"[connectors/websocket_connector.py shutdown] {self.get_job_type()} connector shut down")
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get the current connection status of the connector
        
        Returns:
            Dict[str, Any]: Connection status information
        """
        # Explicitly create and return a Dict[str, Any] to satisfy type checking
        result: Dict[str, Any] = {
            "connected": self.connected,
            "service": self.get_job_type(),
            "details": {},
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
