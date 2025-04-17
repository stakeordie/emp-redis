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
        # Try direct import
        try:
            from websocket_connector import WebSocketConnector as DirectWebSocketConnector
            WebSocketConnector = DirectWebSocketConnector
            logger.info(f"[comfyui_connector.py] Successfully imported WebSocketConnector via direct import")
        except ImportError as e3:
            logger.error(f"[comfyui_connector.py] Failed to import WebSocketConnector: {e3}")
            raise ImportError(f"Could not import WebSocketConnector. Make sure it's loaded first: {e3}")

# Import logger - this should be available in all environments
from core.utils.logger import logger

class ComfyUIConnector(WebSocketConnector):
    """Connector for ComfyUI service"""
    
    # Set the connector name to match the environment variable
    # Updated: 2025-04-07T15:50:00-04:00
    connector_name = "comfyui"
    
    def __init__(self):
        # Call the parent class's __init__ method
        super().__init__()
        
        """Initialize the ComfyUI connector"""
        # ComfyUI connection settings (support both namespaced and non-namespaced)
        self.host = os.environ.get("WORKER_COMFYUI_HOST", os.environ.get("COMFYUI_HOST", "localhost"))
        self.port = int(os.environ.get("WORKER_COMFYUI_PORT", os.environ.get("COMFYUI_PORT", "8188")))
        self.use_ssl = os.environ.get("WORKER_COMFYUI_USE_SSL", os.environ.get("COMFYUI_USE_SSL", "false")).lower() in ("true", "1", "yes")
        
        # Connection management settings
        # Updated: 2025-04-07T15:56:00-04:00 - Added option to control connection persistence
        self.keep_connection_open = os.environ.get("WORKER_COMFYUI_KEEP_CONNECTION", os.environ.get("COMFYUI_KEEP_CONNECTION", "false")).lower() in ("true", "1", "yes")
        
        # Authentication settings
        self.username = os.environ.get("WORKER_COMFYUI_USERNAME", os.environ.get("COMFYUI_USERNAME"))
        self.password = os.environ.get("WORKER_COMFYUI_PASSWORD", os.environ.get("COMFYUI_PASSWORD"))
        
        # Log which variables we're using
        logger.info(f"[comfyui_connector.py __init__] Using environment variables:")
        logger.info(f"[comfyui_connector.py __init__] WORKER_COMFYUI_HOST/COMFYUI_HOST: {self.host}")
        logger.info(f"[comfyui_connector.py __init__] WORKER_COMFYUI_PORT/COMFYUI_PORT: {self.port}")
        logger.info(f"[comfyui_connector.py __init__] WORKER_COMFYUI_USE_SSL/COMFYUI_USE_SSL: {self.use_ssl}")
        logger.info(f"[comfyui_connector.py __init__] WORKER_COMFYUI_KEEP_CONNECTION/COMFYUI_KEEP_CONNECTION: {self.keep_connection_open}")
        
        logger.info(f"[comfyui_connector.py __init__] Initializing connector")
        logger.info(f"[comfyui_connector.py __init__] Username environment variable: {'set' if self.username else 'not set'}")
        
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

        # ComfyUI WebSocket URL
        protocol = "wss" if self.use_ssl else "ws"
        self.ws_url = f"{protocol}://{self.host}:{self.port}/ws"

        # ComfyUI-specific attributes
        self.client_id = None
        self.prompt_id = None
        
        # Set connection details for status reporting
        self.connection_details = {
            "host": self.host,
            "port": self.port,
            "client_id": self.client_id,
            "ws_url": self.ws_url,
            "last_prompt_id": self.prompt_id
        }
    
    async def _on_connect(self) -> None:
        """Handle ComfyUI-specific connection steps"""
        # For ComfyUI, we don't need to do anything special on connect
        # In the future, we could wait for the client_id message here
        pass
    
    async def validate_connection(self):
        """Quick method to check connection without full workflow processing"""
        try:
            # Just validate configuration without connecting
            protocol = "wss" if self.use_ssl else "ws"
            ws_url = f"{protocol}://{self.host}:{self.port}/ws"
            logger.info(f"[comfyui_connector.py validate_connection()] Configuration valid: {ws_url}")
            return True
        except Exception as e:
            logger.error(f"[comfyui_connector.py validate_connection()] Configuration validation failed: {str(e)}")
            return False

    async def initialize(self) -> bool:
        """Initialize the connector
        
        Returns:
            bool: True if initialization was successful, False otherwise
        """
        # Don't establish a connection during initialization
        # Just verify configuration is valid
        try:
            # Validate configuration
            protocol = "wss" if self.use_ssl else "ws"
            ws_url = f"{protocol}://{self.host}:{self.port}/ws"
            logger.info(f"[comfyui_connector.py initialize()] ComfyUI connector initialized with URL: {ws_url}")
            return True
        except Exception as e:
            # Log the issue but don't prevent worker from starting
            logger.warning(f"[comfyui_connector.py initialize()] Initialization error: {e}")
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
    
    async def send_workflow(self, workflow_data: Dict[str, Any]) -> Optional[str]:
        """Send workflow data to ComfyUI
        
        Args:
            workflow_data: The workflow data to send
            
        Returns:
            Optional[str]: The prompt ID if successful, None otherwise
        """
        # Updated: 2025-04-17T14:50:00-04:00 - Enhanced diagnostic logging
        if not self.connected or self.ws is None:
            logger.error(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Cannot send workflow: not connected")
            logger.debug(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Connection state: connected={self.connected}, ws={self.ws}, ws_closed={self.ws.closed if self.ws else True}")
            return None
            
        try:
            # Log connection state before sending
            ws_state = "closed" if self.ws.closed else "open"
            logger.info(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: WebSocket state before sending: {ws_state}")
            
            # Create the prompt message
            prompt_message = {
                "type": "prompt",
                "data": workflow_data
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
            logger.info(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Workflow sent in {send_duration:.2f}s, waiting for response")
            
            # Check connection state after sending
            if self.ws.closed:
                logger.error(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: WebSocket closed immediately after sending workflow")
                raise Exception("WebSocket closed immediately after sending workflow")
            
            # Wait for the prompt response with timeout
            logger.debug(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Waiting for response with 30s timeout")
            try:
                response = await asyncio.wait_for(self.ws.receive_json(), timeout=30.0)
                logger.debug(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Received response: {response}")
            except asyncio.TimeoutError:
                logger.error(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Timeout waiting for response after 30s")
                raise Exception("Timeout waiting for ComfyUI response after sending workflow")
            
            # Check if the response is valid
            if response.get("type") == "prompt":
                # Get the prompt ID
                self.prompt_id = response.get("data", {}).get("prompt_id")
                logger.info(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Workflow sent successfully, prompt ID: {self.prompt_id}")
                return self.prompt_id
            else:
                logger.error(f"[comfyui_connector.py send_workflow] COMFYUI_STATUS: Invalid response from ComfyUI: {response}")
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
        node_progress = {}
        final_result = None
        job_completed = False
        
        # Send initial progress update
        await send_progress_update(job_id, 0, "queued", "Waiting for ComfyUI workflow")
        logger.info(f"[comfyui_connector.py _monitor_service_progress] Workflow queued in ComfyUI")
        
        # Process messages from ComfyUI
        try:
            # Set a timeout for the entire monitoring process
            max_monitoring_time = 600  # 10 minutes max
            
            logger.info(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: Starting message processing loop with {max_monitoring_time}s max duration")
            
            # Use a timeout to prevent infinite waiting
            while not job_completed and (time.time() - monitoring_start_time) < max_monitoring_time:
                # Check if connection is still valid
                if self.ws is None or self.ws.closed:
                    logger.error(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: WebSocket connection closed during monitoring")
                    raise Exception("WebSocket connection closed during monitoring")
                
                # Check for inactivity
                time_since_last_message = time.time() - last_message_time
                if time_since_last_message > 60:  # 1 minute without messages
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
                    logger.debug(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: Waiting for next message with 30s timeout")
                    msg = await asyncio.wait_for(self.ws.receive(), timeout=30.0)
                    last_message_time = time.time()
                    message_count += 1
                    
                    logger.debug(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: Received message #{message_count}, type={msg.type}")
                    
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        # Parse the message data
                        data = json.loads(msg.data)
                        msg_type = data.get('type', 'unknown')
                        
                        logger.debug(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: Message #{message_count} - type={msg_type}")
                        
                        # Handle different message types
                        if msg_type == 'progress':
                            # Update node progress
                            node_id = data.get('data', {}).get('node')
                            progress = data.get('data', {}).get('progress', 0)
                            
                            if node_id is not None:
                                node_progress[node_id] = progress
                                logger.debug(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: Node {node_id} progress: {progress}")
                            
                            # Dynamic progress calculation (10-90%)
                            if node_progress:
                                avg_progress = min(90, 10 + (sum(node_progress.values()) / len(node_progress) * 80))
                                await send_progress_update(job_id, int(avg_progress), "processing", f"Progress across {len(node_progress)} nodes")
                                logger.debug(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: Overall progress: {avg_progress:.1f}%")
                                
                        elif msg_type == 'executing' and data.get('data', {}).get('node') == None:
                            job_completed = True
                            final_result = data.get('data', {})
                            logger.info(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: Workflow execution completed after {message_count} messages")
                            logger.debug(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: Final data: {data}")
                            await send_progress_update(job_id, 100, "finalizing", "Workflow execution completed")
                            break
                            
                        elif msg_type == 'execution_error':
                            error_details = data.get('data', {}).get('exception_message', 'Unknown error')
                            logger.error(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: Execution error: {error_details}")
                            logger.debug(f"[comfyui_connector.py _monitor_service_progress] COMFYUI_STATUS: Error data: {data}")
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
                total_time = time.time() - monitoring_start_time
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
        total_time = time.time() - monitoring_start_time
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
        # Updated: 2025-04-17T14:55:00-04:00 - Enhanced diagnostic logging
        process_start_time = time.time()
        logger.info(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: Processing ComfyUI job {job_id}")
        
        # Log payload size but not full content which could be large
        if isinstance(payload, dict) and 'prompt' in payload:
            node_count = len(payload.get('prompt', {}))
            logger.info(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: Job payload contains {node_count} nodes")
        
        try:
            # Check if connection is still valid before proceeding
            # Updated: 2025-04-17T14:05:00-04:00 - Added connection validation before processing
            # Updated: 2025-04-17T14:55:00-04:00 - Enhanced diagnostic logging
            if self.connection_error is not None:
                error_msg = f"Connection error detected before processing: {str(self.connection_error)}"
                logger.error(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: {error_msg}")
                await send_progress_update(job_id, 0, "error", error_msg)
                raise self.connection_error
            
            if self.ws is None:
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
            
            # Send workflow to ComfyUI
            logger.info(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: Sending workflow to ComfyUI")
            prompt_id = await self.send_workflow(payload)
            
            if not prompt_id:
                error_msg = "Failed to send workflow to ComfyUI"
                logger.error(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: {error_msg}")
                await send_progress_update(job_id, 0, "error", error_msg)
                raise Exception(error_msg)
            
            logger.info(f"[comfyui_connector.py _process_service_job] COMFYUI_STATUS: Workflow sent successfully, prompt_id={prompt_id}")
            
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
            
            return result
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