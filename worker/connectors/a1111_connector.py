#!/usr/bin/env python3
# A1111 REST connector for the EmProps Redis Worker
# Created: 2025-04-07T23:18:27-04:00
import sys
import os

# Add the parent directory to the Python path
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if parent_dir is not None:
    sys.path.insert(0, parent_dir)

# Add the worker directory to the Python path
worker_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if worker_dir is not None:
    sys.path.insert(0, worker_dir)

import json
import asyncio
import aiohttp
import time
from typing import Dict, Any, Optional, Union, Callable

# Try direct imports first (for Docker container)
try:
    from worker.connectors.rest_sync_connector import RESTSyncConnector
except ImportError:
    # Fall back to package imports (for local development)
    from ..connectors.rest_sync_connector import RESTSyncConnector
from core.utils.logger import logger

class A1111Connector(RESTSyncConnector):
    """Connector for Automatic1111 Stable Diffusion Web UI REST API"""
    
    # Version identifier to verify code deployment
    VERSION = "2025-04-17-14:10-improved-timeout-handling"
    
    # Class attribute to identify the connector type
    # This should match the name used in the WORKER_CONNECTORS environment variable
    connector_name = "a1111"
    
    def __init__(self):
        """Initialize the A1111 connector"""
        # Call parent constructor to initialize base REST connector
        super().__init__()
        
        # Override REST API connection settings with A1111-specific ones
        self.host = os.environ.get("WORKER_A1111_HOST", "localhost")
        self.port = os.environ.get("WORKER_A1111_PORT", "3001")
        self.base_url = f"http://{self.host}:{self.port}"
        self.api_prefix = "/sdapi/v1"
        # Use the connector name for job_type
        self.job_type = os.environ.get("WORKER_A1111_JOB_TYPE", os.environ.get("A1111_JOB_TYPE", "a1111"))
        
        # Authentication settings - use ComfyUI environment variables
        self.username = os.environ.get("WORKER_COMFYUI_USERNAME", os.environ.get("COMFYUI_USERNAME"))
        self.password = os.environ.get("WORKER_COMFYUI_PASSWORD", os.environ.get("COMFYUI_PASSWORD"))
        
        # Connection timeout settings
        # Updated: 2025-04-17T14:10:00-04:00 - Added configurable connection timeout
        self.connection_timeout = float(os.environ.get("WORKER_A1111_CONNECTION_TIMEOUT", os.environ.get("A1111_CONNECTION_TIMEOUT", "30.0")))
        self.request_timeout = aiohttp.ClientTimeout(total=self.connection_timeout)
        
        # Log which variables we're using
        logger.info(f"[a1111_connector.py __init__] Using environment variables:")
        logger.info(f"[a1111_connector.py __init__] WORKER_A1111_HOST: {self.host}")
        logger.info(f"[a1111_connector.py __init__] WORKER_A1111_PORT: {self.port}")
        logger.info(f"[a1111_connector.py __init__] Base URL: {self.base_url}")
        logger.info(f"[a1111_connector.py __init__] API Prefix: {self.api_prefix}")
        logger.info(f"[a1111_connector.py __init__] WORKER_A1111_JOB_TYPE/A1111_JOB_TYPE: {self.job_type}")
        logger.info(f"[a1111_connector.py __init__] Connection timeout: {self.connection_timeout}s")
        logger.info(f"[a1111_connector.py __init__] Username environment variable: {'set' if self.username else 'not set'}")
        
        # Update connection details
        self.connection_details = {
            "host": self.host,
            "port": self.port,
            "base_url": self.base_url,
            "api_prefix": self.api_prefix,
            "connection_timeout": self.connection_timeout
        }
    
    def get_job_type(self) -> str:
        """Get the job type that this connector handles
        
        Returns:
            str: The job type string
        """
        return self.job_type
    
    def get_capabilities(self) -> Dict[str, Any]:
        """Get connector-specific capabilities
        
        Returns:
            Dict[str, Any]: Capabilities dictionary to be merged with worker capabilities
        """
        return {
            "a1111_version": self.VERSION,
            "supports_synchronous": True,
            "timeout": self.timeout,
            "supports_txt2img": True,
            "supports_img2img": True,
            "supports_custom_endpoints": True
        }
    
    async def process_job(self, websocket, job_id: str, payload: Dict[str, Any], send_progress_update) -> Dict[str, Any]:
        """Process a job using the A1111 REST API
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
            job_id: The ID of the job to process
            payload: The job payload containing endpoint, method, and payload
            send_progress_update: Function to send progress updates
            
        Returns:
            Dict[str, Any]: Job result
        """
        try:
            # Set current job ID for tracking
            self.current_job_id = job_id
            logger.info(f"[a1111_connector.py process_job] Processing job {job_id}")
            
            # Create session if it doesn't exist with proper timeout
            # Updated: 2025-04-17T14:10:00-04:00 - Added timeout to client session
            if self.session is None:
                self.session = aiohttp.ClientSession(timeout=self.request_timeout)
            
            # Send initial progress update
            await send_progress_update(job_id, 0, "started", f"Starting {self.get_job_type()} job")
            
            # Extract endpoint, method, and payload from the job payload
            endpoint = payload.get("endpoint", "")
            method = payload.get("method", "post").lower()
            request_payload = payload.get("payload", "{}")
            
            # If payload is a string, try to parse it as JSON
            if isinstance(request_payload, str):
                try:
                    request_payload = json.loads(request_payload)
                except json.JSONDecodeError as e:
                    logger.warning(f"[a1111_connector.py process_job] Failed to parse payload as JSON: {str(e)}")
                    # Keep payload as string if it can't be parsed
            
            # Construct the full URL with API prefix
            # Ensure we don't have double slashes between api_prefix and endpoint
            if endpoint.startswith('/'):
                endpoint = endpoint[1:]
            url = f"{self.base_url}{self.api_prefix}/{endpoint}"
            
            # Log detailed request information for debugging
            logger.info(f"[a1111_connector.py process_job] Sending {method.upper()} request to {url}")
            logger.info(f"[a1111_connector.py process_job] Request payload: {json.dumps(request_payload)[:1000]}")
            logger.info(f"[a1111_connector.py process_job] Using timeout: {self.connection_timeout}s")
            
            # Send progress update
            await send_progress_update(job_id, 10, "processing", f"Sending {method.upper()} request to A1111 API")
            
            # Prepare request data
            request_data = {
                "job_id": job_id,
                **request_payload
            }
            
            # [2025-05-19T21:30:00-04:00] Implement progress polling for A1111 jobs
            # This allows us to show progress during long-running image generation and prevent timeouts
            progress_polling_task = None
            
            # [2025-05-19T21:37:00-04:00] Define the progress polling function
            # Only send updates when progress actually changes
            async def poll_progress():
                progress_url = f"{self.base_url}{self.api_prefix}/progress"
                last_progress = 0
                last_eta = 0
                last_update_time = time.time()
                
                try:
                    while True:
                        # Poll the progress endpoint every 5 seconds
                        try:
                            async with self.session.get(progress_url, headers=self._get_headers()) as progress_response:
                                if progress_response.status == 200:
                                    progress_data = await progress_response.json()
                                    progress = progress_data.get('progress', 0)
                                    # Convert from 0-1 to 0-100 scale
                                    progress_percent = int(progress * 100)
                                    eta = progress_data.get('eta_relative', 0)
                                    
                                    # Only send update if progress has changed significantly
                                    # or if ETA has changed significantly
                                    progress_changed = abs(progress_percent - last_progress) >= 5
                                    eta_changed = abs(eta - last_eta) >= 5.0
                                    
                                    if progress_changed or eta_changed:
                                        last_progress = progress_percent
                                        last_eta = eta
                                        last_update_time = time.time()
                                        
                                        # Scale to 10-90 range to leave room for start/end updates
                                        scaled_progress = 10 + int(progress_percent * 0.8)
                                        
                                        await send_progress_update(
                                            job_id, 
                                            scaled_progress, 
                                            "processing", 
                                            f"Generating image: {progress_percent}% complete, ETA: {eta:.1f}s"
                                        )
                                    
                                    # If generation is complete, stop polling
                                    if progress_data.get('completed', False):
                                        break
                        except Exception as e:
                            logger.warning(f"[a1111_connector.py poll_progress] Error polling progress: {str(e)}")
                            # We don't send an update here - if there's a real problem, the main request will time out
                            # which is the correct behavior
                        
                        # Wait before polling again (1 second)
                        await asyncio.sleep(1.0)
                except Exception as e:
                    logger.warning(f"[a1111_connector.py poll_progress] Error in progress polling: {str(e)}")
            
            # Use asyncio.wait_for to implement a more reliable timeout
            # Updated: 2025-04-17T14:11:00-04:00 - Added asyncio.wait_for for better timeout handling
            try:
                # Start the progress polling task before sending the main request
                progress_polling_task = asyncio.create_task(poll_progress())
                
                # Send request to A1111 API with the appropriate HTTP method
                start_time = time.time()
                
                # Choose the appropriate HTTP method
                http_method = getattr(self.session, method, self.session.post)
                
                # Create the request coroutine
                request_coroutine = http_method(
                    url,
                    headers=self._get_headers(),
                    json=request_data if method != "get" else None,
                    params=request_data if method == "get" else None,
                    timeout=self.timeout  # Keep this for backward compatibility
                )
                
                # Execute the request with a timeout - we use a longer timeout now since we have polling
                async with await asyncio.wait_for(request_coroutine, timeout=300.0) as response:
                    elapsed_time = time.time() - start_time
                    
                    # Send progress update
                    await send_progress_update(job_id, 50, "processing", f"Received response from A1111 API in {elapsed_time:.2f}s")
                    
                    # Check response status
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"[a1111_connector.py process_job] Error response from A1111 API: {response.status} - {error_text}")
                        await send_progress_update(job_id, 100, "error", f"A1111 API error: {response.status}")
                        return {
                            "status": "failed",
                            "error": f"A1111 API returned status {response.status}: {error_text}"
                        }
                    
                    # Parse response with timeout
                    # Updated: 2025-04-17T14:11:00-04:00 - Added timeout for response parsing
                    result = await asyncio.wait_for(response.json(), timeout=self.connection_timeout)
                    logger.info(f"[a1111_connector.py process_job] Received successful response from A1111 API")
                    
                    # Send completion update
                    await send_progress_update(job_id, 100, "completed", "Job completed successfully")
                    
                    return {
                        "status": "success",
                        "output": result
                    }
                    
            except asyncio.TimeoutError:
                # Updated: 2025-04-17T14:11:00-04:00 - Improved timeout error handling
                logger.error(f"[a1111_connector.py process_job] Request timed out after {self.connection_timeout} seconds")
                await send_progress_update(job_id, 100, "error", f"Request timed out after {self.connection_timeout} seconds")
                return {
                    "status": "failed",
                    "error": f"Request timed out after {self.connection_timeout} seconds"
                }
                
        except asyncio.TimeoutError:
            # This handles the outer timeout
            logger.error(f"[a1111_connector.py process_job] Request timed out after {self.connection_timeout} seconds")
            await send_progress_update(job_id, 100, "error", f"Request timed out after {self.connection_timeout} seconds")
            return {
                "status": "failed",
                "error": f"Request timed out after {self.connection_timeout} seconds"
            }
        except aiohttp.ClientConnectorError as e:
            # Updated: 2025-04-17T14:12:00-04:00 - Added specific handling for connection errors
            error_msg = f"Connection error to A1111 API at {self.base_url}: {str(e)}"
            logger.error(f"[a1111_connector.py process_job] {error_msg}")
            await send_progress_update(job_id, 100, "error", error_msg)
            return {
                "status": "failed",
                "error": error_msg
            }
        except Exception as e:
            logger.error(f"[a1111_connector.py process_job] Error processing job {job_id}: {str(e)}")
            await send_progress_update(job_id, 100, "error", str(e))
            return {
                "status": "failed",
                "error": str(e)
            }
        finally:
            # Updated: 2025-04-17T14:12:00-04:00 - Always clear current job ID
            logger.info(f"[a1111_connector.py process_job] Completed job {job_id}")
            self.current_job_id = None
