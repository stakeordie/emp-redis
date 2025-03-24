#!/usr/bin/env python3
# ComfyUI connector for the EmProps Redis Worker
import os
import json
import asyncio
import aiohttp
import base64
from typing import Dict, Any, Optional, Union, Callable

from connector_interface import ConnectorInterface
from core.utils.logger import logger

class ComfyUIConnector(ConnectorInterface):
    """Connector for ComfyUI service"""
    
    def __init__(self):
        # Call the parent class's __init__ method
        super().__init__()
        
        """Initialize the ComfyUI connector"""
        # ComfyUI connection settings
        self.host = os.environ.get("COMFYUI_HOST", "localhost")
        self.port = int(os.environ.get("COMFYUI_PORT", "8188"))
        self.use_ssl = os.environ.get("COMFYUI_USE_SSL", "false").lower() in ("true", "1", "yes")
        
        # Authentication settings
        self.username = os.environ.get("COMFYUI_USERNAME")
        self.password = os.environ.get("COMFYUI_PASSWORD")
        
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
    
    async def _generate_bearer_token(self):
        """Async method to generate bearer token"""
        # Log initial authentication attempt details
        logger.info("[comfyui_connector.py _generate_bearer_token] Attempting to generate bearer token")
        logger.info(f"[comfyui_connector.py _generate_bearer_token] Username: {'*' * len(self.username) if self.username else 'Not provided'}")
        logger.info(f"[comfyui_connector.py _generate_bearer_token] Password: {'*' * len(self.password) if self.password else 'Not provided'}")
        
        try:
            # Use aiohttp for async HTTP request
            async with aiohttp.ClientSession() as session:
                # Construct authentication payload
                credentials = f"{self.username}:{self.password}"
                encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
                # Construct authentication URL
                auth_url = f"{'https' if self.use_ssl else 'http'}://{self.host}:{self.port}/api/login"

                headers = {
                    "Authorization": f"Basic {encoded_credentials}",
                    "Content-Type": "application/json"
                }
                
                # Log detailed request information
                logger.info(f"[comfyui_connector.py _generate_bearer_token] Authentication Request Details: {headers}")
                logger.info(f"[comfyui_connector.py _generate_bearer_token] URL: {auth_url}")
                
                # Perform authentication request with detailed logging
                try:
                    async with session.post(
                        auth_url, 
                        headers=headers, 
                        raise_for_status=True
                    ) as response:
                        # Log full response details
                        logger.info(f"[comfyui_connector.py _generate_bearer_token] Response Status: {response.status}")
                        logger.info(f"[comfyui_connector.py _generate_bearer_token] Response Headers: {dict(response.headers)}")
                        
                        try:
                            data = await response.json()
                            logger.info(f"[comfyui_connector.py _generate_bearer_token] Response Body: {data}")
                            
                            # Extract token
                            token = data.get('token')
                            
                            if token:
                                logger.info("[comfyui_connector.py _generate_bearer_token] Bearer token generated successfully")
                                return token
                            else:
                                logger.error("[comfyui_connector.py _generate_bearer_token Error] No token in authentication response")
                                return None
                        except ValueError as json_error:
                                text_response = await response.text()
                                logger.error(f"[comfyui_connector.py _generate_bearer_token] JSON Parsing Error: {str(json_error)}")
                                logger.error(f"[comfyui_connector.py _generate_bearer_token] Raw Response: {text_response}")
                                return None

                except aiohttp.ClientResponseError as e:
                    # Log detailed error information
                    logger.error(f"[comfyui_connector.py _generate_bearer_token Error] Authentication HTTP Error:")
                    logger.error(f"Status: {e.status}")
                    logger.error(f"Message: {str(e)}")
                    return None
        
        except Exception as e:
            logger.error(f"[comfyui_connector.py _generate_bearer_token Error] Token generation error: {str(e)}")
            return None
    
    async def connect(self) -> bool:
        logger.info(f"[comfyui_connector.py connect()] Attempting to connect to {self.ws_url}")
        logger.info(f"[comfyui_connector.py connect()] Bearer Token: {self.bearer_token}")
        logger.info(f"[comfyui_connector.py connect()] Username provided: {'Yes' if self.username else 'No'}")

        self.connected = False

        try:
            # Generate bearer token if not exists
            if not self.bearer_token:
                token = await self._generate_bearer_token()
                if not token:
                    logger.error("[comfyui_connector.py connect()] Authentication failed")
                    return False
                self.bearer_token = token

            # Log WebSocket connection details
            logger.info(f"[comfyui_connector.py connect()] WebSocket URL: {self.ws_url}")
            logger.info(f"[comfyui_connector.py connect()] Authorization Header: {self.bearer_token}")
            
            # Close existing session if it exists
            if hasattr(self, 'session') and self.session:
                await self.session.close()
            
            # Create session if not exists
            headers = {"Authorization": self.bearer_token}


            self.session = aiohttp.ClientSession(headers=headers)
            
            # Connect to ComfyUI WebSocket
            logger.info(f"[comfyui_connector.py connect()] Connecting to ComfyUI at {self.ws_url}")

            try:
                self.ws = await self.session.ws_connect(
                    self.ws_url, 
                    headers={"Authorization": self.bearer_token}
                )
                self.connected = True
            except Exception as e:
                logger.error(f"[comfyui_connector.py connect()] Error connecting to ComfyUI: {str(e)}")
                return False
            
            # Wait for client_id message
            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        if data.get('type') == 'client_id':
                            self.client_id = data.get('data', {}).get('client_id')
                            logger.info(f"[comfyui_connector.py connect()] Connected to ComfyUI with client_id: {self.client_id}")
                            return True
                    except Exception as e:
                        logger.error(f"[comfyui_connector.py connect()] Error processing message: {str(e)}")
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"[comfyui_connector.py connect() .ERROR] WebSocket connection closed with exception {self.ws.exception()}")
                    break
            
            return False

        except Exception as e:
            logger.error(f"[comfyui_connector.py connect() Exception] Error connecting to ComfyUI: {str(e)}")
            return False

    async def validate_connection(self):
        """
        Quick method to check connection without full workflow processing.
        Can be implemented differently based on ComfyUI's API capabilities.
        """
        if not self.connected:
            await self.connect()
        
        # Add a lightweight check, e.g.:
        # - Ping endpoint
        # - Check server status
        # - Validate authentication

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
            logger.warning(f"Initial connection validation failed: {e}")
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
                'prompt': workflow_data.get('prompt', {}),
                'client_id': self.client_id
            }
        }
        
        # Send prompt to ComfyUI
        if self.ws is None:
            raise Exception("WebSocket connection is not established")
        await self.ws.send_str(json.dumps(prompt_message))
        logger.info(f"[COMFYUI] Sent workflow to ComfyUI")
        
        # Wait for prompt_queued message to get prompt_id
        async for msg in self.ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data.get('type') == 'prompt_queued':
                    self.prompt_id = data.get('data', {}).get('prompt_id')
                    logger.info(f"[COMFYUI] Prompt queued with ID: {self.prompt_id}")
                    if self.prompt_id is None:
                        raise Exception("Failed to queue workflow in ComfyUI")
                    return self.prompt_id
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"[COMFYUI] WebSocket connection closed with exception {self.ws.exception()}")
                raise Exception(f"ComfyUI WebSocket error: {self.ws.exception()}")
        
        raise Exception("Failed to queue workflow in ComfyUI")
    
    async def monitor_progress(self, job_id: str, send_progress_update: Callable) -> Dict[str, Any]:
        """Monitor ComfyUI job progress and forward updates
        
        Args:
            job_id: The ID of the job being processed
            send_progress_update: Function to send progress updates
            
        Returns:
            Dict[str, Any]: Job result
        """
        if not self.connected or self.ws is None:
            raise Exception("Not connected to ComfyUI")
        
        # Initialize progress tracking
        execution_started = False
        node_progress = {}
        overall_progress = 0
        
        # Send initial progress update
        await send_progress_update(job_id, 0, "started", "Starting ComfyUI workflow")
        
        try:
            # Monitor ComfyUI messages
            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    
                    # Handle different message types from ComfyUI
                    if data.get('type') == 'executing':
                        execution_started = True
                        node_id = data.get('data', {}).get('node')
                        await send_progress_update(job_id, 10, "processing", f"Executing node {node_id}")
                    
                    elif data.get('type') == 'progress':
                        node_id = data.get('data', {}).get('node')
                        progress = data.get('data', {}).get('progress', 0)
                        node_progress[node_id] = progress
                        
                        # Calculate overall progress (10-90%)
                        if node_progress:
                            avg_progress = sum(node_progress.values()) / len(node_progress)
                            overall_progress = 10 + int(avg_progress * 80)  # Scale to 10-90%
                            await send_progress_update(job_id, overall_progress, "processing", 
                                                     f"Processing workflow ({len(node_progress)} nodes)")
                    
                    elif data.get('type') == 'executed':
                        # A node has completed execution
                        node_id = data.get('data', {}).get('node')
                        node_progress[node_id] = 1.0  # Mark as complete
                        
                        # Recalculate overall progress
                        if node_progress:
                            avg_progress = sum(node_progress.values()) / len(node_progress)
                            overall_progress = 10 + int(avg_progress * 80)
                            await send_progress_update(job_id, overall_progress, "processing", 
                                                     f"Processing workflow ({len(node_progress)} nodes)")
                    
                    elif data.get('type') == 'execution_error':
                        error_msg = data.get('data', {}).get('exception_message', 'Unknown error')
                        logger.error(f"[COMFYUI] Execution error: {error_msg}")
                        await send_progress_update(job_id, overall_progress, "error", f"Error: {error_msg}")
                        return {
                            "status": "failed",
                            "error": error_msg
                        }
                    
                    elif data.get('type') == 'execution_cached':
                        await send_progress_update(job_id, 90, "finalizing", "Using cached results")
                    
                    elif data.get('type') == 'status':
                        status_data = data.get('data', {})
                        if 'status' in status_data and status_data['status'].get('exec_info', {}).get('queue_remaining', 0) == 0:
                            # Check if this is our prompt_id and it's completed
                            history = status_data['status'].get('exec_info', {}).get('executed', [])
                            if self.prompt_id in history:
                                # Workflow completed
                                await send_progress_update(job_id, 100, "completed", "Workflow completed")
                                
                                # Get the results from history
                                result_data = await self.get_results()
                                return {
                                    "status": "success",
                                    "output": result_data
                                }
                
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"[COMFYUI] WebSocket connection closed with exception {self.ws.exception()}")
                    return {
                        "status": "failed",
                        "error": f"ComfyUI WebSocket error: {self.ws.exception()}"
                    }
        
        except Exception as e:
            logger.error(f"[COMFYUI] Error monitoring progress: {str(e)}")
            return {
                "status": "failed",
                "error": str(e)
            }
    
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
        """Process a ComfyUI job
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
            job_id: The ID of the job to process
            payload: The job payload
            send_progress_update: Function to send progress updates
            
        Returns:
            Dict[str, Any]: Job result
        """
        try:
            logger.info(f"[COMFYUI] Processing job {job_id}")
            
            # Connect to ComfyUI if not already connected
            if not self.connected:
                success = await self.connect()
                if not success:
                    raise Exception("Failed to connect to ComfyUI")
            
            # Send workflow to ComfyUI
            await self.send_workflow(payload)
            
            # Monitor progress and get results
            result = await self.monitor_progress(job_id, send_progress_update)
            
            return result
        except Exception as e:
            logger.error(f"[COMFYUI] Error processing job {job_id}: {str(e)}")
            return {
                "status": "failed",
                "error": str(e)
            }
    
    async def shutdown(self) -> None:
        """Clean up resources when worker is shutting down"""
        logger.info("[COMFYUI] Shutting down ComfyUI connector")
        
        if self.ws is not None:
            await self.ws.close()
            self.ws = None
        
        if self.session is not None:
            await self.session.close()
            self.session = None
        
        self.connected = False
        logger.info("[COMFYUI] ComfyUI connector shut down")
