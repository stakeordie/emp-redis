#!/usr/bin/env python3
# ComfyUI connector for the EmProps Redis Worker
# Created: 2025-04-07T11:05:00-04:00
# Updated: 2025-04-07T15:06:00-04:00 - Fixed import order

import os
import json
import asyncio
import aiohttp
import time
import sys
from typing import Dict, Any, Optional, Union, Callable

# Import logger early for diagnostics
from core.utils.logger import logger

# [2025-05-23T09:51:00-04:00] Added standardized message size configuration
# Import from websocket_connector if available, otherwise define locally
try:
    from .websocket_connector import MAX_WS_MESSAGE_SIZE_MB, MAX_WS_MESSAGE_SIZE_BYTES
    logger.info(f"[2025-05-23T09:51:15-04:00] Imported WebSocket message size limits from websocket_connector: {MAX_WS_MESSAGE_SIZE_MB}MB")
except ImportError:
    # Define consistent size limits as environment variables with defaults
    MAX_WS_MESSAGE_SIZE_MB = int(os.environ.get('MAX_WS_MESSAGE_SIZE_MB', 100))  # 100MB default
    MAX_WS_MESSAGE_SIZE_BYTES = MAX_WS_MESSAGE_SIZE_MB * 1024 * 1024
    logger.info(f"[2025-05-23T09:51:30-04:00] Defined local WebSocket message size limits: {MAX_WS_MESSAGE_SIZE_MB}MB")

# Updated import approach - uses proper package imports
# Updated: 2025-04-07T15:04:00-04:00

# Import ConnectorInterface first - this should be available in all environments
# Updated: 2025-04-07T15:05:00-04:00 - Fixed import order and lint errors
ConnectorInterface = None
try:
    # First try relative import from parent package
    from ..connector_interface import ConnectorInterface as ParentConnectorInterface
    ConnectorInterface = ParentConnectorInterface
    logger.info(f"[comfyui_connector.py] Successfully imported ConnectorInterface via relative import from parent package")
except ImportError as e:
    # Fall back to direct import if not in a package context
    try:
        from worker.connector_interface import ConnectorInterface as WorkerConnectorInterface
        ConnectorInterface = WorkerConnectorInterface
        logger.info(f"[comfyui_connector.py] Successfully imported ConnectorInterface via worker package import")
    except ImportError as e2:
        try:
            from connector_interface import ConnectorInterface as DirectConnectorInterface
            ConnectorInterface = DirectConnectorInterface
            logger.info(f"[comfyui_connector.py] Successfully imported ConnectorInterface via direct import")
        except ImportError as e3:
            # Last resort - try absolute import
            import sys
            logger.error(f"[comfyui_connector.py] Failed to import ConnectorInterface: {e3}")
            logger.error(f"[comfyui_connector.py] Python path: {sys.path}")
            raise ImportError(f"Could not import ConnectorInterface: {e3}")

# Now import WebSocketConnector - this should be loaded by the connector_loader first
WebSocketConnector = None
try:
    # First try relative import from same package
    from .websocket_connector import WebSocketConnector as RelativeWebSocketConnector
    WebSocketConnector = RelativeWebSocketConnector
    logger.info(f"[comfyui_connector.py] Successfully imported WebSocketConnector via relative import")
except ImportError as e:
    # Fall back to worker package import
    try:
        from worker.connectors.websocket_connector import WebSocketConnector as WorkerWebSocketConnector
        WebSocketConnector = WorkerWebSocketConnector
        logger.info(f"[comfyui_connector.py] Successfully imported WebSocketConnector via worker package import")
    except ImportError as e2:
        # [2025-05-25T15:30:00-04:00] Fixed import path for WebSocketConnector
        try:
            # Import from the same directory
            from .websocket_connector import WebSocketConnector
            logger.info(f"[comfyui_connector.py] Successfully imported WebSocketConnector from local directory")
        except ImportError as e3:
            logger.error(f"[comfyui_connector.py] Failed to import WebSocketConnector: {e3}")
            raise ImportError(f"Could not import WebSocketConnector. Make sure it's loaded first: {e3}")

# Import logger - this should be available in all environments
from core.utils.logger import logger

# [2025-05-25T15:30:00-04:00] Added type annotation import for proper inheritance
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .websocket_connector import WebSocketConnector

class ComfyUIConnector(WebSocketConnector):
    """Connector for ComfyUI service"""
    
    # Set the connector name to match the environment variable
    # Updated: 2025-04-07T15:50:00-04:00
    connector_name = "comfyui"
    
    # Version tracking
    # Updated: 2025-04-25T15:35:00-04:00 - Added improved connection error handling
    VERSION = "2025-04-25-15:35-connection-error-handling"
    
    def __init__(self):
        # Call the parent class's __init__ method first
        super().__init__()
        
        # ComfyUI connection settings (support both namespaced and non-namespaced)
        self.host = os.environ.get("WORKER_COMFYUI_HOST", os.environ.get("COMFYUI_HOST", "localhost"))
        self.port = int(os.environ.get("WORKER_COMFYUI_PORT", os.environ.get("COMFYUI_PORT", "8188")))
        self.use_ssl = os.environ.get("WORKER_COMFYUI_USE_SSL", os.environ.get("COMFYUI_USE_SSL", "false")).lower() in ("true", "1", "yes")
        
        # Connection management settings
        self.keep_connection_open = os.environ.get("WORKER_COMFYUI_KEEP_CONNECTION", os.environ.get("COMFYUI_KEEP_CONNECTION", "false")).lower() in ("true", "1", "yes")
        
        # Authentication settings
        self.username = os.environ.get("WORKER_COMFYUI_USERNAME", os.environ.get("COMFYUI_USERNAME"))
        self.password = os.environ.get("WORKER_COMFYUI_PASSWORD", os.environ.get("COMFYUI_PASSWORD"))
        
        # ComfyUI-specific attributes
        # 2025-04-17-19:36 - Fixed initialization of ComfyUI-specific attributes
        self.client_id = None
        self.prompt_id = None
        
        # Log which variables we're using
        logger.info(f"[comfyui_connector.py __init__] Using environment variables:")
        logger.info(f"[comfyui_connector.py __init__] WORKER_COMFYUI_HOST/COMFYUI_HOST: {self.host}")
        logger.info(f"[comfyui_connector.py __init__] WORKER_COMFYUI_PORT/COMFYUI_PORT: {self.port}")
        logger.info(f"[comfyui_connector.py __init__] WORKER_COMFYUI_USE_SSL/COMFYUI_USE_SSL: {self.use_ssl}")
        logger.info(f"[comfyui_connector.py __init__] WORKER_COMFYUI_KEEP_CONNECTION/COMFYUI_KEEP_CONNECTION: {self.keep_connection_open}")
        
        # Get the WebSocket URL using the _get_connection_url method
        ws_url = self._get_connection_url()
        logger.info(f"[comfyui_connector.py __init__] WebSocket URL: {ws_url}")
        
        logger.info(f"[comfyui_connector.py __init__] Initializing connector")
        logger.info(f"[comfyui_connector.py __init__] Username environment variable: {'set' if self.username else 'not set'}")
        
        # Set connection details for status reporting
        self.connection_details = {
            "host": self.host,
            "port": self.port,
            "client_id": self.client_id,
            "ws_url": ws_url,
            "last_prompt_id": self.prompt_id
        }
    
    def _get_connection_url(self) -> str:
        """Get the WebSocket connection URL for ComfyUI
        
        Returns:
            str: The WebSocket connection URL
        """
        # 2025-04-17-15:54 - Added missing _get_connection_url method
        protocol = "wss" if self.use_ssl else "ws"
        return f"{protocol}://{self.host}:{self.port}/ws"
    
    def _get_connection_headers(self) -> Dict[str, str]:
        """Get the headers for the WebSocket connection
        
        Returns:
            Dict[str, str]: The headers for the WebSocket connection
        """
        # 2025-04-17-15:54 - Added missing _get_connection_headers method
        headers = {}
        
        # Add authentication headers if credentials are provided
        if self.username and self.password:
            import base64
            auth_string = f"{self.username}:{self.password}"
            auth_bytes = auth_string.encode('ascii')
            base64_bytes = base64.b64encode(auth_bytes)
            base64_auth = base64_bytes.decode('ascii')
            headers['Authorization'] = f'Basic {base64_auth}'
            
        return headers
    
    async def _on_connect(self) -> None:
        """Handle ComfyUI-specific connection steps"""
        # For ComfyUI, we don't need to do anything special on connect
        # In the future, we could wait for the client_id message here
        pass
    
    async def validate_connection(self):
        """Quick method to check connection without full workflow processing
        
        Returns:
            bool: True if connection is valid
            
        Raises:
            Exception: If connection fails for any reason
        """
        # 2025-04-25-17:55 - Updated to use a much shorter timeout (3 seconds) for connection validation
        # Actually test the connection to the ComfyUI server
        protocol = "wss" if self.use_ssl else "ws"
        ws_url = f"{protocol}://{self.host}:{self.port}/ws"
        # 2025-04-25-18:05 - Added eye-catching log entry for connection validation attempt
        logger.info(f"""[comfyui_connector.py validate_connection()] 
╔══════════════════════════════════════════════════════════════════════════════╗
║ COMFYUI CONNECTION VALIDATION ATTEMPT                                        ║
║ URL: {ws_url}                                                                ║
║ Timeout: 3.0s                                                                ║
║ Time: {time.strftime('%Y-%m-%d %H:%M:%S')}                                   ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
        
        # Create a session and try to connect with a very short timeout
        async with aiohttp.ClientSession() as session:
            try:
                # Use a very short timeout for the connection test - fail fast if server is unreachable
                connection_timeout = aiohttp.ClientTimeout(total=3.0)  # 3 second timeout
                
                # Try to connect to the WebSocket endpoint
                headers = self._get_connection_headers()
                # [2025-05-23T09:52:00-04:00] Updated to use standardized message size limit
                logger.info(f"[2025-05-23T09:52:15-04:00] Using WebSocket message size limit: {MAX_WS_MESSAGE_SIZE_MB}MB ({MAX_WS_MESSAGE_SIZE_BYTES} bytes)")
                
                async with session.ws_connect(
                    ws_url, 
                    headers=headers,
                    # [2025-05-25T15:30:00-04:00] Fixed timeout type for ws_connect
                    timeout=aiohttp.ClientWSTimeout(ws_receive=connection_timeout.total),
                    max_msg_size=MAX_WS_MESSAGE_SIZE_BYTES  # Use standardized message size limit
                ) as ws:
                    # Successfully connected, now close it
                    await ws.close()
                    # 2025-04-25-18:05 - Added eye-catching log entry for successful connection validation
                    logger.info(f"""[comfyui_connector.py validate_connection()] 
╔══════════════════════════════════════════════════════════════════════════════╗
║ COMFYUI CONNECTION VALIDATION SUCCESS!!! ✓✓✓                                 ║
║ URL: {ws_url}                                                                ║
║ Connection test completed successfully                                       ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
                    return True
                    
            except asyncio.TimeoutError as e:
                error_msg = f"Connection timeout after 3s: {ws_url}"
                # 2025-04-25-18:05 - Added eye-catching log entry for connection validation timeout
                logger.error(f"""[comfyui_connector.py validate_connection()] 
╔══════════════════════════════════════════════════════════════════════════════╗
║ COMFYUI CONNECTION VALIDATION FAILED!!! ✗✗✗                                  ║
║ URL: {ws_url}                                                                ║
║ Error: CONNECTION TIMEOUT after 3s                                           ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
                raise Exception(error_msg) from e
                
            except aiohttp.ClientConnectorError as e:
                error_msg = f"Cannot connect to ComfyUI server at {self.host}:{self.port}: {str(e)}"
                # 2025-04-25-18:05 - Added eye-catching log entry for connection validation error
                logger.error(f"""[comfyui_connector.py validate_connection()] 
╔══════════════════════════════════════════════════════════════════════════════╗
║ COMFYUI CONNECTION VALIDATION FAILED!!! ✗✗✗                                  ║
║ URL: {ws_url}                                                                ║
║ Error: CONNECTION ERROR - Cannot connect to server                           ║
║ Details: {str(e)}                                                            ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
                raise Exception(error_msg) from e
                
            except aiohttp.WSServerHandshakeError as e:
                error_msg = f"Authentication failed or server rejected connection: {str(e)}"
                logger.error(f"[comfyui_connector.py validate_connection()] {error_msg}")
                raise Exception(error_msg) from e
                
            except aiohttp.ClientError as e:
                error_msg = f"Connection error: {str(e)}"
                logger.error(f"[comfyui_connector.py validate_connection()] {error_msg}")
                raise Exception(error_msg) from e
                
            except Exception as e:
                error_msg = f"Connection test failed: {str(e)}"
                logger.error(f"[comfyui_connector.py validate_connection()] {error_msg}")
                raise Exception(error_msg) from e

    async def initialize(self) -> bool:
        """Initialize the connector
        
        Returns:
            bool: True if initialization was successful, False otherwise
        """
        # 2025-04-25-17:55 - Updated to better handle connection errors
        try:
            # Validate configuration
            protocol = "wss" if self.use_ssl else "ws"
            ws_url = f"{protocol}://{self.host}:{self.port}/ws"
            logger.info(f"[comfyui_connector.py initialize()] ComfyUI connector initializing with URL: {ws_url}")
            
            # Test the connection - will raise an exception if connection fails
            try:
                await self.validate_connection()
                logger.info(f"[comfyui_connector.py initialize()] ComfyUI connection test successful")
                # Clear any previous connection errors
                self.connection_error = None
                return True
            except Exception as e:
                # Log the connection error but allow worker to start
                logger.warning(f"[comfyui_connector.py initialize()] ComfyUI connection test failed: {str(e)}")
                logger.warning(f"[comfyui_connector.py initialize()] Worker will start but ComfyUI jobs will fail until connection is restored")
                # Store the connection error so jobs will fail immediately
                self.connection_error = e
                return True  # Still return True to allow worker to start
        except Exception as e:
            # Log the issue but don't prevent worker from starting
            logger.warning(f"[comfyui_connector.py initialize()] Initialization error: {e}")
            self.connection_error = e
            return True  # Still return True to allow worker to continue
    
    def get_job_type(self) -> str:
        """Get the job type that this connector handles
        
        Returns:
            str: The job type string
        """
        return "comfyui"
    
    def get_capabilities(self) -> Dict[str, Any]:
        """Get connector-specific capabilities
        
        Returns:
            Dict[str, Any]: Capabilities dictionary to be merged with worker capabilities
        """
        return {
            "comfyui_version": "1.0.0",
            "supports_workflows": True,
            "supports_images": True
        }
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get the current connection status of the connector
        
        Returns:
            Dict[str, Any]: Connection status information
        """
        # Update connection details
        self.connection_details = {
            "host": self.host,
            "port": self.port,
            "client_id": self.client_id,
            "ws_url": self.ws_url,
            "last_prompt_id": self.prompt_id
        }
        
        # Use the base class implementation with explicit type casting
        result: Dict[str, Any] = super().get_connection_status()
        return result
    
    async def broadcast_service_request(self, websocket, job_id: str, request_type: str, request_content: Dict[str, Any]) -> None:
        """Broadcast service request details to clients and monitors
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
            job_id: The ID of the job being processed
            request_type: The type of request (e.g., "comfyui_workflow")
            request_content: The content of the request
        """
        try:
            # Create a message to broadcast
            message = {
                "type": "service_request",
                "worker_id": self.worker_id if hasattr(self, "worker_id") else "unknown",
                "job_id": job_id,
                "service": self.get_job_type(),
                "request_type": request_type,
                "timestamp": time.time(),
                "content": request_content
            }
            
            # Send the message to the Redis Hub for broadcasting
            logger.info(f"[comfyui_connector.py broadcast_service_request] Broadcasting {request_type} request for job {job_id}")
            await websocket.send(json.dumps(message))
            
            logger.info(f"[comfyui_connector.py broadcast_service_request] Successfully broadcast {request_type} request")
        except Exception as e:
            error_type = type(e).__name__
            logger.error(f"[comfyui_connector.py broadcast_service_request] Error broadcasting request: {error_type} - {str(e)}")
            # Don't raise the exception - this is a non-critical feature
    
    async def send_workflow(self, workflow_data: Dict[str, Any]) -> Optional[str]:
        """Send workflow data to ComfyUI
        
        Args:
            workflow_data: The workflow data to send
            
        Returns:
            Optional[str]: The prompt ID if successful, None otherwise
        """
        # Updated: 2025-04-17-19:58 - Fixed to handle ComfyUI WebSocket protocol correctly
        if not self.connected or self.ws is None:
            logger.error(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Cannot send workflow: not connected")
            logger.debug(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Connection state: connected={self.connected}, ws={self.ws}, ws_closed={self.ws.closed if self.ws else True}")
            return None
            
        try:
            # Log connection state before sending
            ws_state = "closed" if self.ws.closed else "open"
            logger.info(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: WebSocket state before sending: {ws_state}")
            
            # If we don't have a client_id yet, we need to wait for it first
            if not hasattr(self, 'client_id') or self.client_id is None:
                logger.info(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Waiting for client_id message")
                try:
                    response = await asyncio.wait_for(self.ws.receive_json(), timeout=10.0)
                    logger.debug(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Received initial message: {response}")
                    
                    # Check if it's a client_id message
                    if response.get("type") == "client_id":
                        self.client_id = response.get("data", {}).get("client_id")
                        logger.info(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Received client_id: {self.client_id}")
                    else:
                        logger.warning(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Expected client_id message, got: {response}")
                except asyncio.TimeoutError:
                    logger.error(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Timeout waiting for client_id message")
            
            # Create the prompt message with the correct structure
            # Handle both cases where workflow_data might already have the nested structure
            # or might be just the prompt object itself
            # 2025-04-17-20:01 - Added support for both nested and non-nested workflow data formats
            
            # Check if workflow_data already has a nested structure with 'prompt' key
            if 'prompt' in workflow_data and isinstance(workflow_data.get('prompt'), dict):
                # Already in nested format, use as-is but ensure client_id is set
                message_data = workflow_data.copy()
                
                # Make sure extra_data exists and contains client_id
                if 'extra_data' not in message_data:
                    message_data['extra_data'] = {}
                
                # Set client_id in extra_data
                message_data['extra_data']['client_id'] = self.client_id if hasattr(self, 'client_id') else None
                
                logger.debug(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Using pre-nested workflow structure")
            else:
                # Not in nested format, create the proper structure
                message_data = {
                    "prompt": workflow_data,
                    "extra_data": {
                        "client_id": self.client_id if hasattr(self, 'client_id') else None
                    }
                }
                logger.debug(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Created nested workflow structure")
            
            prompt_message = {
                "type": "prompt",
                "data": message_data
            }
            
            # Log workflow details (without the full prompt data which could be large)
            workflow_nodes = len(workflow_data.get('prompt', {}))
            logger.info(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Sending workflow with {workflow_nodes} nodes to ComfyUI")
            
            # Record send time
            send_start_time = time.time()
            
            # Send the prompt message
            logger.info(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Sending workflow to ComfyUI")
            await self.ws.send_json(prompt_message)
            
            # Log successful send
            send_duration = time.time() - send_start_time
            logger.info(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Workflow sent in {send_duration:.2f}s, waiting for prompt_queued response")
            
            # Check connection state after sending
            if self.ws.closed:
                logger.error(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: WebSocket closed immediately after sending workflow")
                raise Exception("WebSocket closed immediately after sending workflow")
            
            # Wait for the prompt_queued message with timeout
            # We need to process multiple messages until we get the prompt_queued one
            timeout = 30.0
            start_time = time.time()
            
            while (time.time() - start_time) < timeout:
                try:
                    # Set a shorter timeout for each individual message
                    response = await asyncio.wait_for(self.ws.receive_json(), timeout=5.0)
                    logger.debug(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Received response: {response}")
                    
                    # Check message type
                    msg_type = response.get("type")
                    
                    if msg_type == "prompt_queued":
                        # Got the prompt_queued message, extract prompt_id
                        self.prompt_id = response.get("data", {}).get("prompt_id")
                        logger.info(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Workflow queued successfully, prompt ID: {self.prompt_id}")
                        # [2025-05-25T15:30:00-04:00] Fixed return type to match function signature
                        return self.prompt_id if self.prompt_id else None
                    elif msg_type == "error":
                        # Error message from ComfyUI
                        error_msg = response.get("data", {}).get("message", "Unknown error")
                        logger.error(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Error from ComfyUI: {error_msg}")
                        raise Exception(f"ComfyUI error: {error_msg}")
                    else:
                        # Other message type, log and continue waiting
                        logger.debug(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Received {msg_type} message, continuing to wait for prompt_queued")
                        
                except asyncio.TimeoutError:
                    # Timeout waiting for this message, but we'll continue until the overall timeout
                    remaining = timeout - (time.time() - start_time)
                    if remaining > 0:
                        logger.debug(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: No message received in 5s, continuing to wait ({remaining:.1f}s remaining)")
                    else:
                        logger.error(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Overall timeout waiting for prompt_queued message")
                        raise Exception("Timeout waiting for ComfyUI prompt_queued response")
            
            # If we get here, we timed out waiting for the prompt_queued message
            logger.error(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Timeout waiting for prompt_queued message")
            return None
                
        except Exception as e:
            error_type = type(e).__name__
            logger.error(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Error sending workflow: {error_type} - {str(e)}")
            # Check connection state after error
            if self.ws:
                ws_state = "closed" if self.ws.closed else "open"
                logger.error(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: WebSocket state after error: {ws_state}")
            # Set connection error to ensure job fails
            self.connection_error = e
            return None
    
    async def _monitor_service_progress(self, job_id: str, send_progress_update: Callable) -> Dict[str, Any]:
        """ComfyUI-specific implementation of progress monitoring
        
        Args:
            job_id (str): The ID of the current job
            send_progress_update (Callable): Function to send progress updates
            
        Returns:
            Dict[str, Any]: Final job result
        """
        # 2025-04-17-19:44 - Focused on monitoring time between status messages
        node_progress = {}
        final_result = None
        job_completed = False
        
        # Initialize tracking variables
        last_message_time = time.time()
        message_count = 0
        
        # Send initial progress update
        await send_progress_update(job_id, 0, "queued", "Waiting for ComfyUI workflow")
        logger.info(f"[comfyui_connector.py _monitor_service_progress] Workflow queued in ComfyUI")
        
        # Process messages from ComfyUI
        try:
            # Set maximum inactivity time
            max_inactivity_time = 120  # 2 minutes without messages is an error
            
            logger.info(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: Starting message processing loop with {max_inactivity_time}s max inactivity time")
            
            # Monitor until job is completed or connection is lost
            while not job_completed:
                # Check if connection is still valid
                if self.ws is None or self.ws.closed:
                    logger.error(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: WebSocket connection closed during monitoring")
                    raise Exception("WebSocket connection closed during monitoring")
                
                # Check for inactivity
                time_since_last_message = time.time() - last_message_time
                if time_since_last_message > max_inactivity_time:
                    logger.error(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: No messages received for {time_since_last_message:.1f}s - exceeds maximum inactivity time of {max_inactivity_time}s")
                    raise Exception(f"Service inactivity timeout - no messages received for {time_since_last_message:.1f}s")
                
                if time_since_last_message > 60:  # Warning at 1 minute
                    logger.warning(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: No messages received for {time_since_last_message:.1f}s")
                    # Send a ping to check connection
                    logger.debug(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: Sending ping to check connection")
                    try:
                        await self.ws.ping()
                        logger.debug(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: Ping sent successfully")
                    except Exception as e:
                        logger.error(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: Error sending ping: {str(e)}")
                        raise Exception(f"Connection check failed: {str(e)}")
                
                # Wait for next message with timeout
                try:
                    # 2025-04-25-17:55 - Updated to use a longer timeout (60 seconds) for waiting for messages
                    # This allows more time for ComfyUI to process the workflow once connected
                    logger.debug(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: Waiting for next message with 60s timeout")
                    msg = await asyncio.wait_for(self.ws.receive(), timeout=60.0)
                    last_message_time = time.time()
                    message_count += 1
                    
                    logger.debug(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: Received message #{message_count}, type={msg.type}")
                    
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        # Parse the message data
                        data = json.loads(msg.data)
                        msg_type = data.get('type', 'unknown')
                        
                        # 2025-04-17-20:22 - Show ComfyUI messages directly with minimal formatting
                        # Only log the full message for non-progress updates to reduce noise
                        if msg_type != 'progress':
                            # Format the message to be more readable
                            message_data = data.get('data', {})
                            logger.info(f"COMFYUI → {msg_type.upper()}: {message_data}")
                        
                        # Handle different message types
                        if msg_type == 'progress':
                            # Update node progress
                            node_id = data.get('data', {}).get('node')
                            progress = data.get('data', {}).get('progress', 0)
                            
                            if node_id is not None:
                                node_progress[node_id] = progress
                                # Don't log every node progress update to reduce noise
                            
                            # Dynamic progress calculation (10-90%)
                            if node_progress:
                                avg_progress = min(90, 10 + (sum(node_progress.values()) / len(node_progress) * 80))
                                await send_progress_update(job_id, int(avg_progress), "processing", f"Progress across {len(node_progress)} nodes")
                                # Only log progress updates every 10%
                                if int(avg_progress) % 10 == 0:
                                    logger.info(f"COMFYUI → PROGRESS: {int(avg_progress)}% complete across {len(node_progress)} nodes")
                                
                        elif msg_type == 'executing' and data.get('data', {}).get('node') == None:
                            job_completed = True
                            final_result = data.get('data', {})
                            logger.info(f"COMFYUI → COMPLETED: Workflow execution completed after {message_count} messages")
                            # Show the final data in a more readable format
                            final_data = data.get('data', {})
                            logger.info(f"COMFYUI → RESULT: {final_data}")
                            await send_progress_update(job_id, 100, "finalizing", "Workflow execution completed")
                            break
                            
                        elif msg_type == 'execution_error':
                            error_details = data.get('data', {}).get('exception_message', 'Unknown error')
                            logger.error(f"COMFYUI → ERROR: {error_details}")
                            # Show the full error data for debugging
                            error_data = data.get('data', {})
                            logger.error(f"COMFYUI → ERROR_DETAILS: {error_data}")
                            await send_progress_update(job_id, 0, "error", f"ComfyUI execution error: {error_details}")
                            raise Exception(f"ComfyUI Execution Error: {error_details}")
                            
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        # Safely get exception message
                        error_msg = "Unknown WebSocket error"
                        try:
                            if self.ws and self.ws.exception():
                                error_msg = str(self.ws.exception())
                        except Exception as e:
                            error_msg = f"Error getting exception: {str(e)}"
                            
                        logger.error(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: WebSocket error: {error_msg}")
                        raise Exception(f"ComfyUI WebSocket error: {error_msg}")
                        
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        logger.error(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: WebSocket connection closed by server")
                        raise Exception("WebSocket connection closed by server")
                        
                    elif msg.type == aiohttp.WSMsgType.CLOSE:
                        logger.error(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: WebSocket close frame received")
                        raise Exception("WebSocket close frame received")
                        
                except asyncio.TimeoutError:
                    # Log timeout but continue - we'll check connection and try again
                    logger.warning(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: Timeout waiting for message after 30s")
                    await send_progress_update(job_id, -1, "processing", "Waiting for ComfyUI response...")
            
            # Check if we timed out the entire monitoring process
            if not job_completed:
                # 2025-04-17-19:45 - Removed reference to undefined monitoring_start_time
                # Calculate time since the beginning of the method using last_message_time as reference
                total_time = time.time() - last_message_time
                logger.error(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: Monitoring timed out after {total_time:.1f}s")
                raise Exception(f"Workflow monitoring timed out after {total_time:.1f} seconds")
                
        except Exception as e:
            error_type = type(e).__name__
            logger.error(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: Error processing messages: {error_type} - {str(e)}")
            # Log connection state
            if self.ws:
                ws_state = "closed" if self.ws.closed else "open"
                logger.error(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: WebSocket state: {ws_state}, messages received: {message_count}")
            # Set connection error to ensure job fails
            self.connection_error = e
            return {"status": "error", "message": str(e)}
        
        # Log successful completion
        # 2025-04-17-19:46 - Removed reference to undefined monitoring_start_time
        # Calculate time since the beginning of the method using last_message_time as reference
        total_time = time.time() - last_message_time
        logger.info(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: Monitoring completed successfully after {total_time:.1f}s with {message_count} messages")
        
        return final_result or {}
    
    async def get_results(self) -> Dict[str, Any]:
        """Get the results of a ComfyUI workflow execution
        
        Returns:
            Dict[str, Any]: The workflow results
        """
        # In a real implementation, you would query the ComfyUI API to get the results
        # For now, we'll return a placeholder
        return {
            "prompt_id": self.prompt_id,
            "images": ["image_url_would_be_here"],
            "metadata": {
                "workflow_completed": True,
                "client_id": self.client_id
            }
        }
    
    async def _process_service_job(self, websocket, job_id: str, payload: Dict[str, Any], send_progress_update) -> Dict[str, Any]:
        """ComfyUI-specific implementation of job processing
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
            job_id: The ID of the job to process
            payload: The job payload
            send_progress_update: Function to send progress updates
            
        Returns:
            Dict[str, Any]: Job result
        """
        # 2025-04-25-18:00 - Updated to better handle connection failures
        process_start_time = time.time()
        logger.info(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: Processing ComfyUI job {job_id}")
        
        # Log payload size but not full content which could be large
        if isinstance(payload, dict) and 'prompt' in payload:
            node_count = len(payload.get('prompt', {}))
            logger.info(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: Job payload contains {node_count} nodes")
        
        try:
            # Check for existing connection errors before even trying to connect
            if self.connection_error is not None:
                error_msg = f"Pre-existing connection error: {str(self.connection_error)}"
                logger.error(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: {error_msg}")
                await send_progress_update(job_id, 0, "error", error_msg)
                raise self.connection_error
            
            # Test the connection before processing the job - will raise exception if connection fails
            # 2025-04-25-18:00 - validate_connection() now raises exceptions on connection failures
            try:
                logger.info(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: Validating connection to ComfyUI server at {self.host}:{self.port}")
                await self.validate_connection()
                logger.info(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: Connection validation successful")
            except Exception as e:
                error_msg = f"Connection validation failed: {str(e)}"
                logger.error(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: {error_msg}")
                await send_progress_update(job_id, 0, "error", error_msg)
                raise
            
            # Double-check connection state
            if not self.connected or self.ws is None:
                error_msg = "WebSocket connection is not established"
                logger.error(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: {error_msg}")
                await send_progress_update(job_id, 0, "error", error_msg)
                raise Exception(error_msg)
                
            if self.ws.closed:
                error_msg = "WebSocket connection is closed"
                logger.error(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: {error_msg}")
                await send_progress_update(job_id, 0, "error", error_msg)
                raise Exception(error_msg)
            
            # Log connection state before sending workflow
            logger.info(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: Connection state before sending: connected={self.connected}, ws_closed={self.ws.closed if self.ws else True}")
            
            # [2025-05-24T13:40:00-04:00] Broadcast the workflow request content to clients and monitors
            # This allows monitoring of what's being sent to ComfyUI
            await self.broadcast_service_request(websocket, job_id, "comfyui_workflow", payload)
            
            # Send workflow to ComfyUI with a short timeout
            # 2025-04-25-17:55 - Updated to use a shorter timeout (5 seconds) for sending workflows
            # This ensures we fail fast if the server is unreachable
            # 2025-04-25-18:05 - Added eye-catching log entry for workflow sending attempt
            logger.info(f"""[comfyui_connector.py _process_service_job] 
╔══════════════════════════════════════════════════════════════════════════════╗
║ COMFYUI SENDING WORKFLOW                                                    ║
║ Host: {self.host}:{self.port}                                                ║
║ Job ID: {job_id}                                                             ║
║ Timeout: 5.0s                                                                ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
            try:
                # Set a short timeout for the send_workflow operation - this should be quick if the server is reachable
                prompt_id = await asyncio.wait_for(self.send_workflow(payload), timeout=5.0)
                if not prompt_id:
                    error_msg = "Failed to get prompt ID from ComfyUI server"
                    # 2025-04-25-18:05 - Added eye-catching log entry for workflow sending failure
                    logger.error(f"""[comfyui_connector.py _process_service_job] 
╔══════════════════════════════════════════════════════════════════════════════╗
║ COMFYUI WORKFLOW SENDING FAILED!!! ✗✗✗                                      ║
║ Host: {self.host}:{self.port}                                                ║
║ Job ID: {job_id}                                                             ║
║ Error: Failed to get prompt ID from ComfyUI server                           ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
                    await send_progress_update(job_id, 0, "error", error_msg)
                    raise Exception(error_msg)
            except asyncio.TimeoutError as e:
                error_msg = f"Timeout sending workflow to ComfyUI server at {self.host}:{self.port} after 5 seconds"
                # 2025-04-25-18:05 - Added eye-catching log entry for workflow sending timeout
                logger.error(f"""[comfyui_connector.py _process_service_job] 
╔══════════════════════════════════════════════════════════════════════════════╗
║ COMFYUI WORKFLOW SENDING FAILED!!! ✗✗✗                                      ║
║ Host: {self.host}:{self.port}                                                ║
║ Job ID: {job_id}                                                             ║
║ Error: TIMEOUT after 5 seconds                                               ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
                await send_progress_update(job_id, 0, "error", error_msg)
                raise Exception(error_msg) from e
            except Exception as e:
                error_msg = f"Error sending workflow: {str(e)}"
                logger.error(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: {error_msg}")
                await send_progress_update(job_id, 0, "error", error_msg)
                raise
            
            if not prompt_id:
                error_msg = "Failed to send workflow to ComfyUI"
                logger.error(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: {error_msg}")
                await send_progress_update(job_id, 0, "error", error_msg)
                raise Exception(error_msg)
            
            # 2025-04-25-18:05 - Added eye-catching log entry for successful workflow sending
            logger.info(f"""[comfyui_connector.py _process_service_job] 
╔══════════════════════════════════════════════════════════════════════════════╗
║ COMFYUI WORKFLOW SENT SUCCESSFULLY!!! ✓✓✓                                    ║
║ Host: {self.host}:{self.port}                                                ║
║ Job ID: {job_id}                                                             ║
║ Prompt ID: {prompt_id}                                                       ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
            
            # Check again if connection is still valid after sending workflow
            # Updated: 2025-04-17T14:05:00-04:00 - Added connection validation after sending workflow
            # Updated: 2025-04-17T14:55:00-04:00 - Enhanced diagnostic logging
            if self.connection_error is not None:
                error_msg = f"Connection error detected after sending workflow: {str(self.connection_error)}"
                logger.error(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: {error_msg}")
                await send_progress_update(job_id, 0, "error", error_msg)
                raise self.connection_error
            
            if self.ws is None or self.ws.closed:
                error_msg = "WebSocket connection lost after sending workflow"
                logger.error(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: {error_msg}")
                await send_progress_update(job_id, 0, "error", error_msg)
                raise Exception(error_msg)
            
            # Call monitor_progress to enable heartbeats and progress tracking
            logger.info(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: Starting progress monitoring for job {job_id}")
            result = await self.monitor_progress(job_id, send_progress_update)
            
            # Calculate total processing time
            process_duration = time.time() - process_start_time
            logger.info(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: Job {job_id} completed in {process_duration:.2f}s")
            
            # [2025-05-25T15:30:00-04:00] Fixed return type to match function signature
            return result if isinstance(result, dict) else {}
        except Exception as e:
            # Enhanced error logging
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: Job processing error: {error_type} - {error_msg}")
            
            # Log connection state
            if self.ws:
                ws_state = "closed" if self.ws.closed else "open"
                logger.error(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: WebSocket state at error: {ws_state}")
            
            # Set connection error to ensure job fails
            self.connection_error = e
            
            # Send error update
            await send_progress_update(job_id, 0, "error", f"ComfyUI processing error: {error_msg}")
            
            # Re-raise to ensure job fails
            raise
        finally:
            # Close the connection after job completion if keep_connection_open is False
            # Updated: 2025-04-07T15:57:00-04:00 - Added connection management after job completion
            if not self.keep_connection_open:
                logger.info(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: Closing connection after job {job_id} completion")
                await self._disconnect()
            else:
                logger.info(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: Keeping connection open after job {job_id} completion")
    
    async def _on_disconnect(self) -> None:
        """Handle ComfyUI-specific disconnection steps"""
        # Reset ComfyUI-specific attributes
        self.client_id = None
        self.prompt_id = None