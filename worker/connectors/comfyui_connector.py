#!/usr/bin/env python3
# ComfyUI connector for the EmProps Redis Worker
import os
import json
import asyncio
import aiohttp
import base64
import time
from typing import Dict, Any, Optional, Union, Callable


from connector_interface import ConnectorInterface
from core.utils.logger import logger

class ComfyUIConnector(ConnectorInterface):
    """Connector for ComfyUI service"""
    
    def __init__(self):
        # Call the parent class's __init__ method
        super().__init__()
        
        """Initialize the ComfyUI connector"""
        # ComfyUI connection settings (support both namespaced and non-namespaced)
        self.host = os.environ.get("WORKER_COMFYUI_HOST", os.environ.get("COMFYUI_HOST", "localhost"))
        self.port = int(os.environ.get("WORKER_COMFYUI_PORT", os.environ.get("COMFYUI_PORT", "8188")))
        self.use_ssl = os.environ.get("WORKER_COMFYUI_USE_SSL", os.environ.get("COMFYUI_USE_SSL", "false")).lower() in ("true", "1", "yes")
        
        # Authentication settings
        self.username = os.environ.get("WORKER_COMFYUI_USERNAME", os.environ.get("COMFYUI_USERNAME"))
        self.password = os.environ.get("WORKER_COMFYUI_PASSWORD", os.environ.get("COMFYUI_PASSWORD"))
        
        # Log which variables we're using
        logger.info(f"[comfyui_connector.py __init__] Using environment variables:")
        logger.info(f"[comfyui_connector.py __init__] WORKER_COMFYUI_HOST/COMFYUI_HOST: {self.host}")
        logger.info(f"[comfyui_connector.py __init__] WORKER_COMFYUI_PORT/COMFYUI_PORT: {self.port}")
        logger.info(f"[comfyui_connector.py __init__] WORKER_COMFYUI_USE_SSL/COMFYUI_USE_SSL: {self.use_ssl}")
        
        logger.info(f"[comfyui_connector.py __init__] Initializing connector")
        logger.info(f"[comfyui_connector.py __init__] Username environment variable: {'set' if self.username else 'not set'}")

        # ComfyUI WebSocket URL
        protocol = "wss" if self.use_ssl else "ws"
        self.ws_url = f"{protocol}://{self.host}:{self.port}/ws"

        self.bearer_token = None
        # Restore these attributes
        self.ws = None
        self.connected = False
        self.client_id = None
        self.prompt_id = None
        self.session = None
    
    async def connect(self) -> bool:
        logger.info(f"[comfyui_connector.py connect()] Attempting to connect to {self.ws_url}")
        logger.info(f"[comfyui_connector.py connect()] Username provided: {'Yes' if self.username else 'No'}")

        self.connected = False

        try:
            # Validate credentials
            if self.username and self.password:
                credentials = f"{self.username}:{self.password}"
                encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
                # Prepare headers with authentication
                headers = {
                    "Authorization": f"Basic {encoded_credentials}",
                    "Upgrade": "websocket",
                    "Connection": "Upgrade",
                    "Sec-WebSocket-Version": "13"
                }
            else:
                # No authentication
                headers = {
                    "Upgrade": "websocket",
                    "Connection": "Upgrade",
                    "Sec-WebSocket-Version": "13"
                }
                
            # Log WebSocket connection details
            logger.info(f"[comfyui_connector.py connect()] WebSocket URL: {self.ws_url}")
            if "Authorization" in headers:
                logger.info(f"[comfyui_connector.py connect()] Authorization Header: {headers['Authorization']}")
            else:
                logger.info(f"[comfyui_connector.py connect()] No authorization header provided")
            
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
            logger.info(f"[comfyui_connector.py connect()] Successfully connected to ComfyUI")
            return True
            # except Exception as e:
            #     logger.error(f"[comfyui_connector.py connect()] Error connecting to ComfyUI: {str(e)}")
            #     return False
            
            # # Wait for client_id message
            # async for msg in self.ws:
            #     if msg.type == aiohttp.WSMsgType.TEXT:
            #         try:
            #             data = json.loads(msg.data)
            #             if data.get('type') == 'client_id':
            #                 self.client_id = data.get('data', {}).get('client_id')
            #                 logger.info(f"[comfyui_connector.py connect()] Connected to ComfyUI with client_id: {self.client_id}")
            #                 return True
            #         except Exception as e:
            #             logger.error(f"[comfyui_connector.py connect()] Error processing message: {str(e)}")
            #     elif msg.type == aiohttp.WSMsgType.ERROR:
            #         logger.error(f"[comfyui_connector.py connect() .ERROR] WebSocket connection closed with exception {self.ws.exception()}")
            #         break
            
            # return False

        except Exception as e:
            logger.error(f"[comfyui_connector.py connect() Exception] Error connecting to ComfyUI: {str(e)}")
            return False

    async def validate_connection(self):
        """
        Quick method to check connection without full workflow processing.
        Can be implemented differently based on ComfyUI's API capabilities.
        """
        try:
            if not self.connected:
                await self.connect()
            return True
        except Exception as e:
            logger.error(f"[comfyui_connector.py validate_connection() Exception] Connection failed: {str(e)}")
            return False

    async def initialize(self) -> bool:
        """Initialize the connector
        
        Returns:
            bool: True if initialization was successful, False otherwise
        """
        try:
        # Optional: Add a timeout or quick connectivity check
        # Don't block worker startup if connection fails
            await asyncio.wait_for(self.validate_connection(), timeout=5.0)
            return True
        except Exception as e:
            # Log the issue but don't prevent worker from starting
            logger.warning(f"[comfyui_connector.py initialize() Exception] Initial connection validation failed: {e}")
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
        return {
            "connected": self.connected,
            "service": "comfyui",
            "details": {
                "host": self.host,
                "port": self.port,
                "client_id": self.client_id,
                "ws_url": self.ws_url,
                "last_prompt_id": self.prompt_id
            }
        }
    
    async def send_workflow(self, workflow_data: Dict[str, Any]) -> Optional[str]:
        """Send workflow data to ComfyUI
        
        Args:
            workflow_data: The workflow data to send
            
        Returns:
            Optional[str]: The prompt ID if successful, None otherwise
        """
        if not self.connected or self.ws is None:
            success = await self.connect()
            if not success:
                raise Exception("Failed to connect to ComfyUI")
        
        # Prepare prompt message
        prompt_message = {
            'type': 'prompt',
            'data': {
                'prompt': workflow_data,
                'extra_data': {
                    'client_id': self.client_id  # Include client ID if needed
                }
            }
        }
        
        logger.info(f"[comfyui_connector.py send_workflow] Sending workflow to ComfyUI: {prompt_message}")

        # Send prompt to ComfyUI
        if self.ws is None:
            raise Exception("WebSocket connection is not established")
        await self.ws.send_str(json.dumps(prompt_message))
        logger.info(f"[comfyui_connector.py send_workflow] Sent workflow to ComfyUI: {prompt_message}")
        
        # Wait for prompt_queued message to get prompt_id
        async for msg in self.ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data.get('type') == 'prompt_queued':
                    self.prompt_id = data.get('data', {}).get('prompt_id')
                    logger.info(f"[comfyui_connector.py send_workflow] Prompt queued with ID: {self.prompt_id}")
                    if self.prompt_id is None:
                        raise Exception("Failed to queue workflow in ComfyUI")
                    # Explicitly return as str to match the return type
                    return str(self.prompt_id)
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"[comfyui_connector.py send_workflow] WebSocket connection closed with exception {self.ws.exception()}")
                raise Exception(f"ComfyUI WebSocket error: {self.ws.exception()}")
        
        # If we get here without returning, something went wrong
        return None
    
    async def monitor_progress(self, job_id: str, send_progress_update: Callable) -> Dict[str, Any]:
        """
        Monitor ComfyUI job progress with comprehensive error and state handling
        
        Args:
            job_id (str): The ID of the current job
            send_progress_update (Callable): Function to send progress updates
        
        Returns:
            Dict[str, Any]: Final job result or error details
        """
        if not self.connected or self.ws is None:
            raise Exception("Not connected to ComfyUI")
        
        final_result = None
        node_progress = {}
        execution_started = False
        job_completed = False
        
        try:
            # Send initial progress update
            await send_progress_update(job_id, 0, "queued", "Waiting for ComfyUI workflow")
            logger.info(f"[comfyui_connector.py monitor_progress] Workflow queued in ComfyUI")
            
            # Use wait_for instead of timeout
            async for msg in self.ws:
                try:
                    # Timeout for each message receive
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        # logger.info(f"[comfyui_connector.py monitor_progress] Received message from ComfyUI: {msg.data}")
                        # Existing message processing logic...
                        data = json.loads(msg.data)

                        if data.get('type') != 'crystools.monitor':
                            logger.info(f"[comfyui_connector.py monitor_progress] Received message from ComfyUI: {msg}")

                        # Forward raw message for full transparency
                        # await send_progress_update(job_id, 0, "raw_message", json.dumps(data))
                        # Comprehensive message type handling
                        if data.get('type') == 'prompt_queued':
                            await send_progress_update(job_id, 5, "queued", "Workflow accepted by ComfyUI")
                            logger.info(f"[comfyui_connector.py monitor_progress] Workflow accepted by ComfyUI")
                        if data.get('type') == 'progress':
                            node_id = data.get('data', {}).get('node')
                            progress = data.get('data', {}).get('value', 0)
                            node_progress[node_id] = progress
                            logger.info(f"[comfyui_connector.py monitor_progress] Progress for node {node_id}: {progress}")    
                            # Dynamic progress calculation (10-90%)
                            if node_progress:
                                avg_progress = min(90, 10 + (sum(node_progress.values()) / len(node_progress) * 80))
                                await send_progress_update(job_id, int(avg_progress), "processing", f"Progress across {len(node_progress)} nodes")
                        if data.get('type') == 'executing' and data.get('data', {}).get('node') == None:
                            job_completed = True
                            final_result = data.get('data', {})
                            logger.debug(f"[comfyui_connector.py monitor_progress] data: {data}")
                            await send_progress_update(job_id, 100, "finalizing", "Workflow execution completed")
                            logger.info(f"[comfyui_connector.py monitor_progress] Workflow execution completed")
                        if data.get('type') == 'execution_error':
                            logger.debug(f"[comfyui_connector.py monitor_progress] data: {data}")
                            await send_progress_update(job_id, 0, "error", str(data))
                            raise Exception(f"ComfyUI Execution Error: {data}")
                    # Check for job completion
                    if job_completed:
                        break
                except asyncio.TimeoutError:
                    logger.error("[COMFYUI] Message receive timed out")
                    await send_progress_update(job_id, 0, "timeout", "Job message receive timed out")
                    break
        except asyncio.TimeoutError:
            logger.error("[COMFYUI] Job monitoring timed out")
            await send_progress_update(job_id, 0, "timeout", "Job exceeded maximum processing time")
        
        except Exception as e:
            logger.error(f"[COMFYUI] Unexpected error: {str(e)}")
            await send_progress_update(job_id, 0, "error", str(e))
        
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
            logger.info(f"[comfyui_connector.py process_job] Processing job {job_id}")
            logger.info(f"[comfyui_connector.py process_job] Job payload: {payload}")
            
            # Connect to ComfyUI if not already connected
            if not self.connected:
                success = await self.connect()
                if not success:
                    raise Exception("Failed to connect to ComfyUI")
            
            # Send workflow to ComfyUI
            logger.info(f"[comfyui_connector.py process_job] Sending workflow to ComfyUI: {payload}")
            await self.send_workflow(payload)
            
            # Monitor progress and get results
            result = await self.monitor_progress(job_id, send_progress_update)
            
            return result
        except Exception as e:
            logger.error(f"[comfyui_connector.py process_job] Error processing job {job_id}: {str(e)}")
            return {
                "status": "failed",
                "error": str(e)
            }
    
    async def monitor_ws_connection(self, websocket, worker_id: str) -> None:
        """Monitor WebSocket connection to ComfyUI and send status updates
        
        This method periodically checks the WebSocket connection to ComfyUI
        and sends status updates to the Redis Hub.
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
            worker_id: The ID of the worker
        """
        # Import here to avoid circular imports
        from core.message_models import MessageModels
        
        # Create message models instance
        message_models = MessageModels()
        
        # Monitor interval in seconds
        monitor_interval = 30
        
        logger.info(f"[comfyui_connector.py monitor_ws_connection] Starting WebSocket connection monitor for worker {worker_id}")
        
        try:
            while True:
                try:
                    # Check if the WebSocket connection is alive
                    connected = self.connected and self.ws is not None
                    
                    # If not connected, try to reconnect
                    if not connected:
                        logger.warning(f"[comfyui_connector.py monitor_ws_connection] WebSocket connection to ComfyUI is down, attempting to reconnect")
                        try:
                            await self.connect()
                            connected = self.connected and self.ws is not None
                        except Exception as e:
                            logger.error(f"[comfyui_connector.py monitor_ws_connection] Failed to reconnect to ComfyUI: {str(e)}")
                    
                    # Get connection details
                    details = {
                        "host": self.host,
                        "port": self.port,
                        "client_id": self.client_id,
                        "ws_url": self.ws_url,
                        "last_prompt_id": self.prompt_id
                    }
                    
                    # Create and send status message
                    status_message = message_models.create_connector_ws_status_message(
                        worker_id=worker_id,
                        connector_type="comfyui",
                        connected=connected,
                        service_name="ComfyUI",
                        details=details,
                        last_ping=time.time() if connected else None
                    )
                    
                    # Send status message to Redis Hub
                    await websocket.send(status_message.model_dump_json())
                    logger.debug(f"[comfyui_connector.py monitor_ws_connection] Sent WebSocket connection status: {connected}")
                    
                except Exception as e:
                    logger.error(f"[comfyui_connector.py monitor_ws_connection] Error monitoring WebSocket connection: {str(e)}")
                
                # Wait for next check
                await asyncio.sleep(monitor_interval)
        except Exception as e:
            logger.error(f"[comfyui_connector.py monitor_ws_connection] Fatal error in WebSocket connection monitor: {str(e)}")
    
    async def shutdown(self) -> None:
        """Clean up resources when worker is shutting down"""
        logger.info("[comfyui_connector.py shutdown] Shutting down ComfyUI connector")
        
        if self.ws is not None:
            await self.ws.close()
            self.ws = None
        
        if self.session is not None:
            await self.session.close()
            self.session = None
        
        self.connected = False
        logger.info("[COMFYUI] ComfyUI connector shut down")
