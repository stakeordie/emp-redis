#!/usr/bin/env python3
# ComfyUI connector for the EmProps Redis Worker
# Created: 2025-04-07T11:05:00-04:00
# Updated: 2025-04-07T15:06:00-04:00 - Fixed import order
# Updated: 2025-05-25T16:00:00-04:00 - Fixed type errors and import structure

import os
import json
import asyncio
import aiohttp
import time
import sys
from typing import Dict, Any, Optional, Union, Callable, List, Tuple, cast, TYPE_CHECKING

# Import logger early for diagnostics
from core.utils.logger import logger

# [2025-05-23T09:51:00-04:00] Added standardized message size configuration
# Define consistent size limits as environment variables with defaults
MAX_WS_MESSAGE_SIZE_MB = int(os.environ.get('MAX_WS_MESSAGE_SIZE_MB', 100))  # 100MB default
MAX_WS_MESSAGE_SIZE_BYTES = MAX_WS_MESSAGE_SIZE_MB * 1024 * 1024

# [2025-05-25T16:00:00-04:00] Fixed import structure to resolve type assignment errors
# Import ConnectorInterface first
ConnectorInterface = None
try:
    # First try relative import from parent package
    from ..connector_interface import ConnectorInterface
except ImportError as e:
    # Fall back to direct import if not in a package context
    try:
        from worker.connector_interface import ConnectorInterface
    except ImportError as e2:
        try:
            from connector_interface import ConnectorInterface
        except ImportError as e3:
            # Last resort - try absolute import
            logger.error(f"[2025-05-25T16:00:00-04:00] Failed to import ConnectorInterface: {e3}")
            logger.error(f"[2025-05-25T16:00:00-04:00] Python path: {sys.path}")
            raise ImportError(f"Could not import ConnectorInterface: {e3}")

# [2025-05-25T16:00:00-04:00] Import WebSocketConnector with a different name to avoid type conflicts
# This prevents the "Cannot assign to a type" error
WebSocketConnectorBase = None
try:
    # Try relative import first (preferred method)
    from .websocket_connector import WebSocketConnector as WebSocketConnectorBase
    logger.info(f"[2025-05-25T16:00:00-04:00] Successfully imported WebSocketConnector via relative import")
except ImportError as e:
    try:
        # Fall back to worker package import
        from worker.connectors.websocket_connector import WebSocketConnector as WebSocketConnectorBase
        logger.info(f"[2025-05-25T16:00:00-04:00] Successfully imported WebSocketConnector via worker package import")
    except ImportError as e2:
        # Add the connectors directory to the path if needed
        connectors_dir = os.path.dirname(os.path.abspath(__file__))
        if connectors_dir not in sys.path:
            sys.path.insert(0, connectors_dir)
        try:
            # Last attempt with absolute import
            import websocket_connector
            WebSocketConnectorBase = websocket_connector.WebSocketConnector
            logger.info(f"[2025-05-25T16:00:00-04:00] Successfully imported WebSocketConnector via absolute import")
        except ImportError as e3:
            logger.error(f"[2025-05-25T16:00:00-04:00] Failed to import WebSocketConnector: {e3}")
            raise ImportError(f"Could not import WebSocketConnector. Make sure it's loaded first: {e3}")

# Ensure we have a valid base class
if WebSocketConnectorBase is None:
    raise ImportError("[2025-05-25T16:00:00-04:00] Failed to import WebSocketConnector through any method")

class ComfyUIConnector(WebSocketConnectorBase):
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
        self.port = os.environ.get("WORKER_COMFYUI_PORT", os.environ.get("COMFYUI_PORT", "8188"))
        self.use_ssl = os.environ.get("WORKER_COMFYUI_USE_SSL", os.environ.get("COMFYUI_USE_SSL", "false")).lower() in ("true", "1", "yes")
        
        # Connection persistence settings
        # Updated: 2025-04-07T16:00:00-04:00 - Added connection persistence control
        self.keep_connection = os.environ.get("WORKER_COMFYUI_KEEP_CONNECTION", "false").lower() in ("true", "1", "yes")
        
        # Timeout settings
        # Updated: 2025-04-25T17:55:00-04:00 - Optimized timeouts for faster failure detection
        self.connection_timeout = int(os.environ.get("WORKER_COMFYUI_CONNECTION_TIMEOUT", "5"))  # 5 seconds for initial connection
        self.validation_timeout = int(os.environ.get("WORKER_COMFYUI_VALIDATION_TIMEOUT", "3"))  # 3 seconds for validation
        self.workflow_timeout = int(os.environ.get("WORKER_COMFYUI_WORKFLOW_TIMEOUT", "5"))  # 5 seconds for workflow sending
        self.message_timeout = int(os.environ.get("WORKER_COMFYUI_MESSAGE_TIMEOUT", "60"))  # 60 seconds for message waiting
        
        # Set up the job type
        self.job_type = "comfyui"
        
        # WebSocket connection
        self.ws = None
        self.session = None
        self.prompt_id = None
        self.client_id = None
        
        # Workflow execution state
        self.execution_start = None
        self.execution_error = None
        
        # Progress tracking
        self.progress = 0
        self.status = "idle"
        
        # Result storage
        self.result_images = []
        
        # Build the base URL
        protocol = "wss" if self.use_ssl else "ws"
        self.ws_url = f"{protocol}://{self.host}:{self.port}/ws"
        
        # Build the API URL
        api_protocol = "https" if self.use_ssl else "http"
        self.api_url = f"{api_protocol}://{self.host}:{self.port}/api"
        
        # Build the base URL for image access
        self.base_url = f"{api_protocol}://{self.host}:{self.port}"
        
        # Set up the connection timeout
        self.connection_timeout_obj = aiohttp.ClientTimeout(total=self.connection_timeout)
        
        # Set up the message timeout
        self.message_timeout_obj = aiohttp.ClientTimeout(total=self.message_timeout)
        
        # Set up the workflow timeout
        self.workflow_timeout_obj = aiohttp.ClientTimeout(total=self.workflow_timeout)
        
        # Set up the validation timeout
        self.validation_timeout_obj = aiohttp.ClientTimeout(total=self.validation_timeout)
    
    async def initialize(self) -> bool:
        """Initialize the connector
        
        Returns:
            bool: True if initialization was successful, False otherwise
        """
        # Validate the connection to ComfyUI
        # Updated: 2025-04-25T15:35:00-04:00 - Added actual connection testing
        try:
            # Test the connection to ComfyUI
            connection_valid = await self.validate_connection()
            if not connection_valid:
                logger.error(f"[comfyui_connector.py initialize] COMFYUI_STATUS: ✗✗✗ FAILED ✗✗✗ - Connection validation failed")
                return False
            
            # Successfully initialized
            logger.info(f"[comfyui_connector.py initialize] COMFYUI_STATUS: ✓✓✓ SUCCESS ✓✓✓ - Connected to ComfyUI at {self.ws_url}")
            return True
            
        except Exception as e:
            # Log the error
            logger.error(f"[comfyui_connector.py initialize] COMFYUI_STATUS: ✗✗✗ FAILED ✗✗✗ - Error initializing ComfyUI connector: {str(e)}")
            return False
    
    async def validate_connection(self) -> bool:
        """Validate the connection to ComfyUI
        
        Returns:
            bool: True if the connection is valid, False otherwise
        """
        # Create a session and try to connect with a very short timeout
        async with aiohttp.ClientSession() as session:
            try:
                # Use a very short timeout for the connection test - fail fast if server is unreachable
                connection_timeout = aiohttp.ClientTimeout(total=3.0)  # 3 second timeout
                
                # Try to connect to the WebSocket endpoint
                headers = self._get_connection_headers()
                # [2025-05-23T09:52:00-04:00] Updated to use standardized message size limit
                logger.info(f"[2025-05-23T09:52:15-04:00] Using WebSocket message size limit: {MAX_WS_MESSAGE_SIZE_MB}MB ({MAX_WS_MESSAGE_SIZE_BYTES} bytes)")
                
                # [2025-05-25T16:00:00-04:00] Fixed timeout type for ws_connect
                # ClientWSTimeout is the correct type for WebSocket connections
                ws_timeout = aiohttp.ClientWSTimeout(ws_receive=connection_timeout.total)
                
                async with session.ws_connect(
                    self.ws_url, 
                    headers=headers,
                    timeout=ws_timeout,
                    max_msg_size=MAX_WS_MESSAGE_SIZE_BYTES  # Use standardized message size limit
                ) as ws:
                    # Successfully connected, now close it
                    await ws.close()
                    # 2025-04-25-18:05 - Added eye-catching log entry for successful connection validation
                    logger.info(f"[comfyui_connector.py validate_connection] COMFYUI_STATUS: ✓✓✓ SUCCESS ✓✓✓ - Connected to ComfyUI at {self.ws_url}")
                    return True
            except Exception as e:
                # 2025-04-25-18:05 - Added eye-catching log entry for failed connection validation
                logger.error(f"[comfyui_connector.py validate_connection] COMFYUI_STATUS: ✗✗✗ FAILED ✗✗✗ - Error connecting to ComfyUI at {self.ws_url}: {str(e)}")
                return False
    
    def _get_connection_headers(self) -> Dict[str, str]:
        """Get the headers for the WebSocket connection
        
        Returns:
            Dict[str, str]: The headers for the WebSocket connection
        """
        return {}
    
    async def shutdown(self) -> None:
        """Shutdown the connector
        
        Returns:
            None
        """
        # Close the WebSocket connection if it's open
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception as e:
                logger.error(f"[comfyui_connector.py shutdown] Error closing WebSocket connection: {str(e)}")
            finally:
                self.ws = None
        
        # Close the session if it's open
        if self.session is not None:
            try:
                await self.session.close()
            except Exception as e:
                logger.error(f"[comfyui_connector.py shutdown] Error closing session: {str(e)}")
            finally:
                self.session = None
    
    def get_job_type(self) -> str:
        """Get the job type that this connector handles
        
        Returns:
            str: The job type string
        """
        return self.job_type
    
    def get_capabilities(self) -> Dict[str, Any]:
        """Get the capabilities of this connector
        
        Returns:
            Dict[str, Any]: The capabilities of this connector
        """
        return {
            "job_type": self.job_type,
            "version": self.VERSION,
            "supports_progress": True,
            "supports_cancel": True,
            "max_concurrent_jobs": 1,  # ComfyUI can only process one job at a time
            "connection_info": {
                "host": self.host,
                "port": self.port,
                "use_ssl": self.use_ssl,
                "ws_url": self.ws_url,
                "api_url": self.api_url,
                "keep_connection": self.keep_connection
            }
        }
    
    async def connect(self) -> bool:
        """Connect to the ComfyUI WebSocket
        
        Returns:
            bool: True if the connection was successful, False otherwise
        """
        # Close any existing connection
        await self.shutdown()
        
        # Create a new session
        self.session = aiohttp.ClientSession()
        
        try:
            # Connect to the WebSocket
            headers = self._get_connection_headers()
            # [2025-05-23T09:52:00-04:00] Updated to use standardized message size limit
            logger.info(f"[2025-05-23T09:52:15-04:00] Using WebSocket message size limit: {MAX_WS_MESSAGE_SIZE_MB}MB ({MAX_WS_MESSAGE_SIZE_BYTES} bytes)")
            
            # [2025-05-25T16:00:00-04:00] Fixed timeout type for ws_connect
            ws_timeout = aiohttp.ClientWSTimeout(ws_receive=self.connection_timeout_obj.total)
            
            self.ws = await self.session.ws_connect(
                self.ws_url, 
                headers=headers,
                timeout=ws_timeout,
                max_msg_size=MAX_WS_MESSAGE_SIZE_BYTES  # Use standardized message size limit
            )
            
            # Get the client ID from the first message
            try:
                async with asyncio.timeout(5):  # 5 second timeout for getting the client ID
                    msg = await self.ws.receive_json()
                    self.client_id = msg.get("sid", None)
                    logger.info(f"[comfyui_connector.py connect] Connected to ComfyUI with client ID: {self.client_id}")
            except asyncio.TimeoutError:
                logger.warning(f"[comfyui_connector.py connect] Timed out waiting for client ID from ComfyUI")
            except Exception as e:
                logger.warning(f"[comfyui_connector.py connect] Error getting client ID from ComfyUI: {str(e)}")
            
            # Successfully connected
            # 2025-04-25-18:05 - Added eye-catching log entry for successful connection
            logger.info(f"[comfyui_connector.py connect] COMFYUI_STATUS: ✓✓✓ SUCCESS ✓✓✓ - Connected to ComfyUI at {self.ws_url}")
            return True
            
        except Exception as e:
            # Log the error
            # 2025-04-25-18:05 - Added eye-catching log entry for failed connection
            logger.error(f"[comfyui_connector.py connect] COMFYUI_STATUS: ✗✗✗ FAILED ✗✗✗ - Error connecting to ComfyUI: {str(e)}")
            
            # Clean up
            await self.shutdown()
            
            # Raise the exception to be handled by the caller
            # Updated: 2025-04-25T17:45:00-04:00 - Always raise exceptions for connection failures
            raise
    
    async def send_workflow(self, workflow: Dict[str, Any]) -> Optional[str]:
        """Send a workflow to ComfyUI
        
        Args:
            workflow: The workflow to send
            
        Returns:
            Optional[str]: The prompt ID if the workflow was queued successfully, None otherwise
        """
        # Reset state
        self.prompt_id = None
        self.result_images = []
        self.execution_error = None
        self.execution_start = time.time()
        
        # Validate the connection before sending the workflow
        # Updated: 2025-04-25T15:35:00-04:00 - Added pre-job connection validation
        try:
            # Test the connection to ComfyUI
            connection_valid = await self.validate_connection()
            if not connection_valid:
                logger.error(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: ✗✗✗ FAILED ✗✗✗ - Connection validation failed")
                raise Exception("ComfyUI connection validation failed")
        except Exception as e:
            logger.error(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: ✗✗✗ FAILED ✗✗✗ - Error validating connection: {str(e)}")
            raise
        
        # Connect to ComfyUI if not already connected
        if self.ws is None or self.session is None:
            try:
                await self.connect()
            except Exception as e:
                logger.error(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: ✗✗✗ FAILED ✗✗✗ - Error connecting to ComfyUI: {str(e)}")
                raise
        
        # Send the workflow
        try:
            # Create the prompt message
            prompt = {
                "prompt": workflow,
                "client_id": self.client_id
            }
            
            # Send the prompt
            await self.ws.send_json({"type": "execute", "data": prompt})
            logger.info(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Sent workflow to ComfyUI")
            
            # Wait for the prompt_queued message
            # Updated: 2025-04-25T17:55:00-04:00 - Using workflow_timeout for faster failure detection
            async with asyncio.timeout(self.workflow_timeout):
                while True:
                    # Get the next message
                    msg = await self.ws.receive_json()
                    
                    # Parse the message
                    msg_type = msg.get("type", "")
                    response = msg.get("data", {})
                    
                    if msg_type == "prompt_queued":
                        # Got the prompt_queued message, extract prompt_id
                        self.prompt_id = response.get("prompt_id")
                        logger.info(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Workflow queued successfully, prompt ID: {self.prompt_id}")
                        # [2025-05-25T16:00:00-04:00] Fixed return type to match function signature
                        return str(self.prompt_id) if self.prompt_id else None
                    elif msg_type == "error":
                        # Error message from ComfyUI
                        error_msg = response.get("message", "Unknown error")
                        logger.error(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Error from ComfyUI: {error_msg}")
                        raise Exception(f"ComfyUI error: {error_msg}")
                    else:
                        # Other message type, log and continue waiting
                        logger.debug(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Received {msg_type} message, continuing to wait for prompt_queued")
                        
        except asyncio.TimeoutError:
            # Timed out waiting for the prompt_queued message
            logger.error(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Timed out waiting for prompt_queued message")
            raise Exception("Timed out waiting for prompt_queued message from ComfyUI")
        except Exception as e:
            # Other error
            logger.error(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Error sending workflow: {str(e)}")
            raise
    
    async def wait_for_completion(self, prompt_id: str) -> Dict[str, Any]:
        """Wait for a workflow to complete
        
        Args:
            prompt_id: The prompt ID to wait for
            
        Returns:
            Dict[str, Any]: The result of the workflow
        """
        # Check if we have a valid prompt ID
        if not prompt_id:
            logger.error(f"[comfyui_connector.py wait_for_completion] COMFYUI_STATUS: No prompt ID provided")
            raise Exception("No prompt ID provided")
        
        # Connect to ComfyUI if not already connected
        if self.ws is None or self.session is None:
            try:
                await self.connect()
            except Exception as e:
                logger.error(f"[comfyui_connector.py wait_for_completion] COMFYUI_STATUS: Error connecting to ComfyUI: {str(e)}")
                raise
        
        # Wait for the execution_complete message
        try:
            # Reset result state
            self.result_images = []
            self.execution_error = None
            
            # Wait for messages
            # Updated: 2025-04-25T17:55:00-04:00 - Using message_timeout for longer waiting
            async with asyncio.timeout(self.message_timeout):
                while True:
                    # Get the next message
                    msg = await self.ws.receive_json()
                    
                    # Parse the message
                    msg_type = msg.get("type", "")
                    response = msg.get("data", {})
                    
                    # Check if this message is for our prompt
                    msg_prompt_id = response.get("prompt_id", None)
                    if msg_prompt_id != prompt_id:
                        # Not for our prompt, ignore
                        continue
                    
                    if msg_type == "executing":
                        # Workflow is executing
                        logger.info(f"[comfyui_connector.py wait_for_completion] COMFYUI_STATUS: Workflow is executing")
                        
                    elif msg_type == "progress":
                        # Progress update
                        self.progress = response.get("value", 0)
                        max_value = response.get("max", 1)
                        if max_value > 0:
                            progress_percent = int((self.progress / max_value) * 100)
                        else:
                            progress_percent = 0
                        logger.debug(f"[comfyui_connector.py wait_for_completion] COMFYUI_STATUS: Progress: {progress_percent}%")
                        
                    elif msg_type == "executed":
                        # Workflow has been executed, but we still need to wait for the images
                        logger.info(f"[comfyui_connector.py wait_for_completion] COMFYUI_STATUS: Workflow executed, waiting for images")
                        
                    elif msg_type == "execution_error":
                        # Error during execution
                        error_msg = response.get("exception_message", "Unknown error")
                        self.execution_error = error_msg
                        logger.error(f"[comfyui_connector.py wait_for_completion] COMFYUI_STATUS: Execution error: {error_msg}")
                        raise Exception(f"ComfyUI execution error: {error_msg}")
                        
                    elif msg_type == "execution_cached":
                        # Execution was cached
                        logger.info(f"[comfyui_connector.py wait_for_completion] COMFYUI_STATUS: Execution cached")
                        
                    elif msg_type == "image":
                        # Got an image
                        image_data = response.get("image", "")
                        filename = response.get("filename", "")
                        subfolder = response.get("subfolder", "")
                        
                        # Add to result images
                        image_url = f"{self.base_url}/view?filename={filename}&subfolder={subfolder}&type=output"
                        self.result_images.append({
                            "url": image_url,
                            "filename": filename,
                            "subfolder": subfolder
                        })
                        
                        logger.info(f"[comfyui_connector.py wait_for_completion] COMFYUI_STATUS: Got image: {filename}")
                        
                    elif msg_type == "status":
                        # Status update
                        status_data = response.get("status", {})
                        
                        # Check if the execution is complete
                        if status_data.get("exec_info", {}).get("queue_remaining", 0) == 0:
                            # All done, return the result
                            execution_time = time.time() - self.execution_start
                            logger.info(f"[comfyui_connector.py wait_for_completion] COMFYUI_STATUS: Execution complete in {execution_time:.2f}s")
                            
                            # Return the result
                            return {
                                "images": self.result_images,
                                "execution_time": execution_time
                            }
                    
                    else:
                        # Other message type, log and continue waiting
                        logger.debug(f"[comfyui_connector.py wait_for_completion] COMFYUI_STATUS: Received {msg_type} message")
                        
        except asyncio.TimeoutError:
            # Timed out waiting for completion
            logger.error(f"[comfyui_connector.py wait_for_completion] COMFYUI_STATUS: Timed out waiting for completion")
            raise Exception("Timed out waiting for workflow completion from ComfyUI")
        except Exception as e:
            # Other error
            logger.error(f"[comfyui_connector.py wait_for_completion] COMFYUI_STATUS: Error waiting for completion: {str(e)}")
            raise
    
    async def process_job(self, job_id: str, job_data: Dict[str, Any], send_progress_update: Callable[[int, str], None]) -> Dict[str, Any]:
        """Process a job
        
        Args:
            job_id: The ID of the job to process
            job_data: The job data
            send_progress_update: A callback function to send progress updates
            
        Returns:
            Dict[str, Any]: The result of the job
        """
        # [2025-05-25T16:00:00-04:00] Fixed return type and error handling
        try:
            # Extract the workflow from the job data
            workflow = job_data.get("workflow", {})
            if not workflow:
                raise Exception("No workflow provided in job data")
            
            # Log the start of processing
            process_start_time = time.time()
            logger.info(f"[comfyui_connector.py process_job] COMFYUI_STATUS: Starting job {job_id}")
            
            # Send initial progress update
            send_progress_update(0, "Starting")
            
            # Send the workflow to ComfyUI
            prompt_id = await self.send_workflow(workflow)
            if not prompt_id:
                raise Exception("Failed to queue workflow in ComfyUI")
            
            # Send progress update
            send_progress_update(10, "Queued")
            
            # Wait for the workflow to complete
            result = await self.wait_for_completion(prompt_id)
            
            # Send final progress update
            send_progress_update(100, "Complete")
            
            # Log the completion
            process_duration = time.time() - process_start_time
            logger.info(f"[comfyui_connector.py process_job] COMFYUI_STATUS: Job {job_id} completed in {process_duration:.2f}s")
            
            # [2025-05-25T16:00:00-04:00] Fixed return type to match function signature
            if not result:
                return {}
            elif isinstance(result, dict):
                return result
            else:
                # Convert to dict if possible
                try:
                    return dict(result)
                except (TypeError, ValueError):
                    return {}
        except Exception as e:
            # Enhanced error logging
            error_type = type(e).__name__
            error_message = str(e)
            
            # Log the error with eye-catching formatting
            logger.error(f"""[comfyui_connector.py process_job] COMFYUI_STATUS: ✗✗✗ FAILED ✗✗✗
            Job ID: {job_id}
            Error Type: {error_type}
            Error Message: {error_message}
            """)
            
            # Re-raise the exception to be handled by the worker
            raise
        finally:
            # Close the connection if we're not keeping it open
            if not self.keep_connection:
                await self.shutdown()
    
    async def cancel_job(self, job_id: str, job_data: Dict[str, Any]) -> bool:
        """Cancel a job
        
        Args:
            job_id: The ID of the job to cancel
            job_data: The job data
            
        Returns:
            bool: True if the job was cancelled successfully, False otherwise
        """
        # Not currently supported by ComfyUI
        logger.warning(f"[comfyui_connector.py cancel_job] COMFYUI_STATUS: Job cancellation not supported by ComfyUI")
        return False
    
    async def _process_service_job(self, job_id: str, job_data: Dict[str, Any], send_progress_update: Callable[[int, str], None]) -> Dict[str, Any]:
        """Process a service job - alias for process_job
        
        Args:
            job_id: The ID of the job to process
            job_data: The job data
            send_progress_update: A callback function to send progress updates
            
        Returns:
            Dict[str, Any]: The result of the job
        """
        return await self.process_job(job_id, job_data, send_progress_update)
