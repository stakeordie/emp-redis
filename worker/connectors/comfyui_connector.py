#!/usr/bin/env python3
# ComfyUI connector for the EmProps Redis Worker
import os
import json
import asyncio
import aiohttp
import time
from typing import Dict, Any, Optional, Union, Callable

import sys
import os

# Add the parent directory to the Python path
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, parent_dir)

# Add the worker directory to the Python path
worker_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, worker_dir)

# Try direct imports first (for Docker container)
try:
    from websocket_connector import WebSocketConnector
except ImportError:
    # Fall back to package imports (for local development)
    from worker.websocket_connector import WebSocketConnector
from core.utils.logger import logger

class ComfyUIConnector(WebSocketConnector):
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
        if not self.connected or self.ws is None:
            raise Exception("Not connected to ComfyUI")
        
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
        async for msg in self.ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)

                if data.get('type') != 'crystools.monitor':
                    logger.info(f"[comfyui_connector.py _monitor_service_progress] Received message from ComfyUI: {msg}")

                # Comprehensive message type handling
                if data.get('type') == 'prompt_queued':
                    await send_progress_update(job_id, 5, "queued", "Workflow accepted by ComfyUI")
                    logger.info(f"[comfyui_connector.py _monitor_service_progress] Workflow accepted by ComfyUI")
                if data.get('type') == 'progress':
                    node_id = data.get('data', {}).get('node')
                    progress = data.get('data', {}).get('value', 0)
                    node_progress[node_id] = progress
                    logger.info(f"[comfyui_connector.py _monitor_service_progress] Progress for node {node_id}: {progress}")    
                    # Dynamic progress calculation (10-90%)
                    if node_progress:
                        avg_progress = min(90, 10 + (sum(node_progress.values()) / len(node_progress) * 80))
                        await send_progress_update(job_id, int(avg_progress), "processing", f"Progress across {len(node_progress)} nodes")
                if data.get('type') == 'executing' and data.get('data', {}).get('node') == None:
                    job_completed = True
                    final_result = data.get('data', {})
                    logger.debug(f"[comfyui_connector.py _monitor_service_progress] data: {data}")
                    await send_progress_update(job_id, 100, "finalizing", "Workflow execution completed")
                    logger.info(f"[comfyui_connector.py _monitor_service_progress] Workflow execution completed")
                    break
                if data.get('type') == 'execution_error':
                    logger.debug(f"[comfyui_connector.py _monitor_service_progress] data: {data}")
                    await send_progress_update(job_id, 0, "error", str(data))
                    raise Exception(f"ComfyUI Execution Error: {data}")
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"[comfyui_connector.py _monitor_service_progress] WebSocket error: {self.ws.exception()}")
                raise Exception(f"ComfyUI WebSocket error: {self.ws.exception()}")
        
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
        logger.info(f"[comfyui_connector.py _process_service_job] Processing ComfyUI job {job_id}")
        logger.info(f"[comfyui_connector.py _process_service_job] Job payload: {payload}")
        
        # Send workflow to ComfyUI
        logger.info(f"[comfyui_connector.py _process_service_job] Sending workflow to ComfyUI")
        await self.send_workflow(payload)
        
        # AI-generated fix: 2025-04-04T20:17:19 - Call monitor_progress to enable heartbeats and progress tracking
        logger.info(f"[comfyui_connector.py _process_service_job] Starting progress monitoring for job {job_id}")
        result = await self.monitor_progress(job_id, send_progress_update)
        
        return result
    
    async def _on_disconnect(self) -> None:
        """Handle ComfyUI-specific disconnection steps"""
        # Reset ComfyUI-specific attributes
        self.client_id = None
        self.prompt_id = None