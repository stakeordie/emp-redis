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
import aiohttp  # Removed unnecessary type ignore
import time
import logging
from typing import Dict, Any, Optional, Union, Callable, cast, List, Tuple
from ..base_worker import BaseWorker

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
    
    # [2025-05-25T21:40:00-04:00] Implemented connector_id property to replace connector_name
    # This provides a cleaner way to identify connectors without type compatibility issues
    @property
    def connector_id(self) -> str:
        """Get the connector identifier used for loading and identification
        
        Returns:
            str: The connector identifier string 'a1111'
        """
        return 'a1111'
    
    def __init__(self):
        """Initialize the A1111 connector"""
        # [2025-05-25T23:53:00-04:00] Call parent constructor first
        # The parent constructor will set job_type to 'rest'
        super().__init__()
        
        # Initialize with parent constructor
        
        # Base URL for the A1111 API
        self.base_url = os.environ.get("WORKER_A1111_URL", "http://localhost:7860")
        
        # [2025-05-25T23:53:00-04:00] CRITICAL FIX: Force job_type to match connector_id
        # This must happen AFTER super().__init__() which sets job_type to 'rest'
        # This is critical for job assignment to work correctly
        self.job_type = self.connector_id
        
        # Check if job type is overridden by environment variable
        env_job_type = os.environ.get("WORKER_A1111_JOB_TYPE", None)
        if env_job_type:
            # Only use environment variable if it matches connector_id
            if env_job_type == self.connector_id:
                self.job_type = env_job_type
            else:
                logger.error(f"[a1111_connector.py] Environment variable WORKER_A1111_JOB_TYPE='{env_job_type}' doesn't match connector_id='{self.connector_id}'. Using connector_id.")
                self.job_type = self.connector_id
        
        # Ensure job_type matches connector_id for consistency
        if self.job_type != self.connector_id:
            logger.error(f"[a1111_connector.py] WARNING: job_type='{self.job_type}' doesn't match connector_id='{self.connector_id}'. This may cause job assignment issues!")
        
        # Override REST API connection settings with A1111-specific ones
        self.host = os.environ.get("WORKER_A1111_HOST", "localhost")
        self.port = os.environ.get("WORKER_A1111_PORT", "3001")
        self.base_url = f"http://{self.host}:{self.port}"
        self.api_prefix = "/sdapi/v1"
        
        # [2025-05-25T23:53:00-04:00] CRITICAL FIX: Force job_type to match connector_id
        # This is critical for job assignment to work correctly
        self.job_type = self.connector_id
        
        # Check if job_type is overridden by environment variables
        env_job_type = os.environ.get("WORKER_A1111_JOB_TYPE", os.environ.get("A1111_JOB_TYPE", None))
        if env_job_type:
            # Only use environment variable if it matches connector_id
            if env_job_type == self.connector_id:
                self.job_type = env_job_type
            else:
                logger.error(f"[a1111_connector.py] Environment job type '{env_job_type}' doesn't match connector_id '{self.connector_id}'. Using connector_id.")
                # CRITICAL: Always use connector_id for job_type
                self.job_type = self.connector_id
            
        # [2025-05-26T21:00:00-04:00] Fixed authentication to use A1111 credentials instead of ComfyUI
        self.username = os.environ.get("WORKER_A1111_USERNAME", os.environ.get("A1111_USERNAME"))
        self.password = os.environ.get("WORKER_A1111_PASSWORD", os.environ.get("A1111_PASSWORD"))
        
        # Log authentication settings (without exposing password)
        if self.username:
            logger.debug(f"[a1111_connector.py __init__()] Using authentication with username: {self.username}")
        else:
            logger.debug(f"[a1111_connector.py __init__()] No authentication credentials provided")
            
        # [2025-05-26T21:20:00-04:00] Added debug logging for authentication settings
        logger.debug(f"[a1111_connector.py __init__()] A1111 authentication configured with username: {self.username or 'None'}")
        if not self.username or not self.password:
            logger.warning(f"[a1111_connector.py __init__()] Missing A1111 authentication credentials - API calls may fail")
        
        # Connection timeout settings
        # Updated: 2025-04-17T14:10:00-04:00 - Added configurable connection timeout
        self.connection_timeout = float(os.environ.get("WORKER_A1111_CONNECTION_TIMEOUT", os.environ.get("A1111_CONNECTION_TIMEOUT", "30.0")))
        self.request_timeout = aiohttp.ClientTimeout(total=self.connection_timeout)
          
        # Update connection details
        self.connection_details = {
            "host": self.host,
            "port": self.port,
            "base_url": self.base_url,
            "api_prefix": self.api_prefix,
            "connection_timeout": self.connection_timeout
        }
        
    # [2025-05-26T21:25:00-04:00] Added custom _get_headers method for A1111 authentication
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for A1111 API requests with proper authentication
        
        Returns:
            Dict[str, str]: Headers for A1111 API requests
        """
        # Create basic headers
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Add authentication if credentials are provided
        if self.username and self.password:
            import base64
            # Format credentials exactly as expected by nginx Basic Auth
            credentials = f"{self.username}:{self.password}"
            # Ensure proper UTF-8 encoding and decoding
            encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
            headers["Authorization"] = f"Basic {encoded_credentials}"
            logger.debug(f"[a1111_connector.py _get_headers()] Created auth header for user: {self.username}")
        else:
            logger.warning(f"[a1111_connector.py _get_headers()] No authentication credentials provided")
            
        return headers
    
    async def health_check(self) -> bool:
        """Check if the A1111 API is available
        
        Returns:
            bool: True if the API is available, False otherwise
        """
        # [2025-05-25T22:40:00-04:00] Added detailed debug logging for A1111 health check
        # [2025-05-25T21:35:00-04:00] Fixed type errors by adding proper None handling
        logger.debug(f"[a1111_connector.py health_check DEBUG] Performing health check for A1111 API")
        logger.debug(f"[a1111_connector.py health_check DEBUG] Health check URL: {self.base_url}/healthz")
        try:
            # Make sure self.session is not None
            if self.session is None:
                logger.error(f"[a1111_connector.py health_check] Session is None, cannot perform health check")
                return False
                
            async with self.session.get(f"{self.base_url}/healthz", headers=self._get_headers()) as response:
                # [2025-05-25T21:55:00-04:00] Explicitly cast to bool to fix type error
                status_code = response.status
                is_healthy = status_code == 200
                return bool(is_healthy)  # Explicit cast to bool
        except Exception as e:
            logger.error(f"[a1111_connector.py health_check] Health check failed: {str(e)}")
            return False
    
    async def check_health(self) -> bool:
        """Check if the A1111 service is running and accessible
        
        Returns:
            bool: True if the service is healthy, False otherwise
        """
        # [2025-05-25T18:45:00-04:00] Added health check method for A1111 service
        # [2025-05-25T21:40:00-04:00] Fixed type errors by adding proper None handling
        try:
            # Get the headers and log them for debugging
            headers = self._get_headers()
            auth_header = headers.get('Authorization', 'None')
            # Mask the actual credentials in the logs
            masked_auth = 'Basic ******' if auth_header.startswith('Basic ') else auth_header
            
            logger.debug(f"[a1111_connector.py check_health()] Checking A1111 health at {self.base_url}{self.api_prefix}/progress")
            logger.debug(f"[a1111_connector.py check_health()] Using authentication header: {masked_auth}")
            
            async with self.session.get(f"{self.base_url}{self.api_prefix}/progress", headers=headers, timeout=5) as response:
                status_code = response.status
                if status_code == 200:
                    logger.debug(f"[a1111_connector.py check_health()] A1111 service is available")
                    return True
                else:
                    # Log more details about the failed response
                    logger.warning(f"[a1111_connector.py check_health()] A1111 service returned status code: {status_code}")
                    try:
                        response_text = await response.text()
                        logger.warning(f"[a1111_connector.py check_health()] Response body: {response_text[:200]}...")
                    except Exception as text_error:
                        logger.warning(f"[a1111_connector.py check_health()] Could not read response body: {str(text_error)}")
                    
                    # Log response headers
                    logger.warning(f"[a1111_connector.py check_health()] Response headers: {dict(response.headers)}")
                    return False
        # [2025-05-26T21:20:00-04:00] Fixed exception handling to catch all error types properly
        except asyncio.TimeoutError:
            logger.error(f"[a1111_connector.py check_health()] A1111 service connection timeout")
            return False
        except Exception as e:
            # [2025-05-26T21:10:00-04:00] Added clear source identification to log messages
            logger.error(f"[a1111_connector.py check_health()] A1111 service health check error: {e}")
            # Log the full exception details for debugging
            logger.debug(f"[a1111_connector.py check_health()] Exception details: {type(e).__name__}: {str(e)}")
            return False
    
    async def initialize(self) -> bool:
        """Initialize the connector
        
        Returns:
            bool: True if initialization was successful, False otherwise
        """
        # [2025-05-25T21:50:00-04:00] Fixed type error by ensuring the method always returns a boolean value
        try:
            # [2025-05-26T21:10:00-04:00] Improved logging with consistent format
            logger.debug(f"[a1111_connector.py initialize()] Initializing A1111 connector with base URL: {self.base_url}")
            logger.debug(f"[a1111_connector.py initialize()] Connection details: base_url={self.base_url}, api_prefix={self.api_prefix}")
            
            # Set up session
            self.session = aiohttp.ClientSession()
            
            # Check if the A1111 service is available
            is_healthy = await self.check_health()
            # A1111 service is not available, but we'll initialize anyway
            if not is_healthy:
                logger.warning(f"[a1111_connector.py initialize()] A1111 service is not available, but connector will be initialized anyway")
            
            # Always return True for now to allow the connector to be used even if A1111 is not running
            # This allows the worker to accept A1111 jobs and queue them until A1111 is available
            return True
        except Exception as e:
            # [2025-05-26T21:10:00-04:00] Fixed duplicate log message
            logger.error(f"[a1111_connector.py initialize()] Error initializing A1111 connector: {str(e)}")
            return False
    
    # [2025-05-26T18:10:00-04:00] Add method to strip base64 images from payloads
    def _strip_base64_images(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Strip base64-encoded images from the payload to reduce message size
        
        Args:
            payload: The original payload that may contain base64-encoded images
            
        Returns:
            Dict[str, Any]: A copy of the payload with base64 images replaced by placeholders
        """
        # Make a deep copy of the payload to avoid modifying the original
        import copy
        stripped_payload = copy.deepcopy(payload)
        
        # Check for init_images in the payload (used in img2img)
        if "init_images" in stripped_payload and isinstance(stripped_payload["init_images"], list):
            # Replace each base64 image with a placeholder
            for i, image in enumerate(stripped_payload["init_images"]):
                if isinstance(image, str) and len(image) > 1000:  # Likely a base64 image
                    image_size = len(image)
                    stripped_payload["init_images"][i] = f"<BASE64_IMAGE_{i}_{image_size}_bytes>"
                    logger.debug(f"[2025-05-26T18:10:00-04:00] [a1111_connector.py] Stripped base64 image of {image_size} bytes from init_images[{i}]")
        
        # Check for image_variable in the payload (another way to specify images)
        if "image_variable" in stripped_payload and stripped_payload["image_variable"] in stripped_payload:
            image_var = stripped_payload["image_variable"]
            if isinstance(stripped_payload[image_var], str) and len(stripped_payload[image_var]) > 1000:
                image_size = len(stripped_payload[image_var])
                stripped_payload[image_var] = f"<BASE64_IMAGE_{image_var}_{image_size}_bytes>"
                logger.debug(f"[2025-05-26T18:10:00-04:00] [a1111_connector.py] Stripped base64 image of {image_size} bytes from {image_var}")
        
        # Check for mask in the payload (used in inpainting)
        if "mask" in stripped_payload and isinstance(stripped_payload["mask"], str) and len(stripped_payload["mask"]) > 1000:
            mask_size = len(stripped_payload["mask"])
            stripped_payload["mask"] = f"<BASE64_MASK_{mask_size}_bytes>"
            logger.debug(f"[2025-05-26T18:10:00-04:00] [a1111_connector.py] Stripped base64 mask of {mask_size} bytes")
        
        return stripped_payload
        
    def get_job_type(self) -> str:
        """Get the job type that this connector handles
        
        Returns:
            str: The job type string that matches connector_id
        """
        # [2025-05-25T21:55:00-04:00] Always return connector_id for proper job assignment
        # This ensures that the worker can receive jobs that match the connector_id
        job_type = self.connector_id
        
        # Update self.job_type to match connector_id for consistency
        if self.job_type != job_type:
            logger.debug(f"[2025-05-25T21:55:00-04:00] Fixing job_type mismatch: '{self.job_type}' -> '{job_type}'")
            self.job_type = job_type
            
        logger.debug(f"[2025-05-25T21:55:00-04:00] A1111Connector.get_job_type() returning: '{job_type}'")
        return job_type
    
    def get_capabilities(self) -> Dict[str, Any]:
        """Get connector-specific capabilities
        
        Returns:
            Dict[str, Any]: Capabilities dictionary to be merged with worker capabilities
        """
        # [2025-05-25T22:40:00-04:00] Added detailed debug logging for A1111 capabilities
        logger.debug(f"[a1111_connector.py get_capabilities DEBUG] Getting A1111 capabilities")
        return {
            "a1111_version": self.VERSION,
            "supports_synchronous": True,
            "timeout": self.timeout,
            "supports_txt2img": True,
            "supports_img2img": True,
            "supports_custom_endpoints": True
        }
    
    # [2025-05-25T10:35:00-04:00] Removed the broadcast_service_request method and replaced with direct message sending
    # This ensures that service request messages are sent using the same mechanism as progress updates
    
    async def process_job(self, websocket, job_id: str, payload: Dict[str, Any], send_progress_update) -> Dict[str, Any]:
        """
        Process a job using the A1111 REST API
        
        Args:
            websocket: WebSocket connection to the Redis hub
            job_id: Unique identifier for the job
            payload: Job payload containing request parameters
            send_progress_update: Function to send progress updates
            
        Returns:
            Dict[str, Any]: Job result
        """
        # [2025-05-25T22:40:00-04:00] Added detailed debug logging for A1111 job processing
        logger.debug(f"[a1111_connector.py process_job DEBUG] Starting to process A1111 job: {job_id}")
        logger.debug(f"[a1111_connector.py process_job DEBUG] Job payload: {json.dumps(payload)[:500]}...")
        logger.debug(f"[a1111_connector.py process_job DEBUG] Connection status: base_url={self.base_url}, api_prefix={self.api_prefix}")
        # [2025-05-20T12:02:05-04:00] Add a flag to track job completion
        # This helps prevent sending progress updates after the job is completed
        job_completed = False
        
        # Wrap the send_progress_update function to check the job_completed flag
        async def safe_send_progress_update(job_id, progress, status, message):
            nonlocal job_completed
            # Don't send progress updates if the job is already completed
            if job_completed and status == "processing":
                return
            # If this is a completion update, set the flag
            if status in ["completed", "failed", "error"]:
                job_completed = True
            # Forward the update
            await send_progress_update(job_id, progress, status, message)
        
        try:
            # Set current job ID for tracking
            self.current_job_id = job_id            
            # Create session if it doesn't exist with proper timeout
            # Updated: 2025-04-17T14:10:00-04:00 - Added timeout to client session
            if self.session is None:
                self.session = aiohttp.ClientSession(timeout=self.request_timeout)
            
            # Send initial progress update
            await safe_send_progress_update(job_id, 0, "started", f"Starting {self.get_job_type()} job")
            
            # Extract endpoint, method, and payload from the job payload
            endpoint = payload.get("endpoint", "")
            method = payload.get("method", "post").lower()
            request_payload = payload.get("payload", "{}")
            
            # If payload is a string, try to parse it as JSON
            if isinstance(request_payload, str):
                try:
                    request_payload = json.loads(request_payload)
                except json.JSONDecodeError as e:
                    logger.error(f"[a1111_connector.py process_job] Failed to parse payload as JSON: {str(e)}")
                    # Keep payload as string if it can't be parsed
            
            # Construct the full URL with API prefix
            # Ensure we don't have double slashes between api_prefix and endpoint
            if endpoint.startswith('/'):
                endpoint = endpoint[1:]
            url = f"{self.base_url}{self.api_prefix}/{endpoint}"
                        
            # Send progress update
            await safe_send_progress_update(job_id, 10, "processing", f"Sending {method.upper()} request to A1111 API")
            
            # Prepare request data
            request_data = {
                "job_id": job_id,
                **request_payload
            }
            
            # [2025-05-25T11:15:00-04:00] IMPORTANT: Create a service request message that will be broadcast to monitors
            try:
                # Log with a very distinctive message to ensure we can see it in the logs
                logger.debug(f"[a1111_connector.py process_job] [2025-05-25T11:15:00-04:00] BROADCASTING SERVICE REQUEST for job {job_id} to endpoint {endpoint}")
                
                # [2025-05-26T18:10:00-04:00] Strip large base64 images from the payload for the service request message
                # This prevents the service request message from becoming too large
                stripped_payload = self._strip_base64_images(request_payload)
                
                # Create a message that will be sent directly to the websocket
                # This bypasses the Hub's message routing and goes directly to the monitor
                service_request_message = {
                    "type": "service_request",  # This is a special message type that the monitor will recognize
                    "timestamp": time.time(),
                    "job_id": job_id,
                    "worker_id": self.worker_id if hasattr(self, "worker_id") else "unknown",
                    "service": self.get_job_type() if hasattr(self, "job_type") else "a1111",
                    "request_type": f"a1111_{endpoint}",
                    "content": {
                        "endpoint": endpoint,
                        "method": method.upper(),
                        "url": url,
                        "payload": stripped_payload
                    }
                }
                
                # Convert to JSON for sending
                message_json = json.dumps(service_request_message)
                message_size = len(message_json)
                
                # Log the message details with very distinctive timestamps
                logger.debug(f"[a1111_connector.py process_job] [2025-05-25T11:15:00-04:00] Sending service request message (size: {message_size} bytes)")
                logger.debug(f"[a1111_connector.py process_job] [2025-05-25T11:15:00-04:00] Message structure: {list(service_request_message.keys())}")
                
                # Send the message directly using the websocket
                # This bypasses the Hub's message routing and goes directly to the monitor
                await websocket.send(message_json)
                
                # [2025-05-25T13:45:00-04:00] Send a progress update message directly
                # A1111Connector doesn't inherit from BaseWorker, so we can't use self.send_progress_update
                progress_message = {
                    "type": "update_job_progress",
                    "job_id": job_id,
                    "worker_id": self.worker_id if hasattr(self, "worker_id") else "unknown",
                    "progress": 10,
                    "status": "processing",
                    "message": f"Sending {method.upper()} request to A1111 API",
                    "timestamp": time.time()
                }
                
                # Convert to JSON and send directly
                progress_json = json.dumps(progress_message)
                await websocket.send(progress_json)
                
                # Log success with very distinctive timestamp
                logger.debug(f"[a1111_connector.py process_job] [2025-05-25T11:15:00-04:00] Successfully sent service request message for job {job_id}")
                
            except Exception as e:
                # Log but don't fail the job if broadcasting fails
                error_type = type(e).__name__
                logger.error(f"[a1111_connector.py process_job] [2025-05-25T11:15:00-04:00] FAILED to send service request: {error_type} - {str(e)}")
                # Continue with the job processing
            
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
                            # [2025-05-25T15:25:00-04:00] Added null check for session to prevent attribute errors
                            if not hasattr(self, 'session') or self.session is None:
                                logger.error(f"[2025-05-25T15:25:00-04:00] Session is None or not initialized in poll_progress")
                                break
                                
                            async with self.session.get(progress_url, headers=self._get_headers()) as progress_response:
                                if progress_response.status == 200:
                                    progress_data = await progress_response.json()
                                    # Cast to avoid None attribute error
                                    progress_data_dict = cast(Dict[str, Any], progress_data)
                                    progress = progress_data_dict.get('progress', 0)
                                    # Convert from 0-1 to 0-100 scale
                                    progress_percent = int(progress * 100)
                                    eta = progress_data_dict.get('eta_relative', 0)
                                    
                                    # Only send update if progress has changed significantly
                                    # or if ETA has changed significantly
                                    progress_changed = abs(progress_percent - last_progress) >= 5
                                    eta_changed = abs(eta - last_eta) >= 5.0
                                    
                                    if progress_changed or eta_changed:
                                        last_progress = progress_percent
                                        last_eta = eta                                        
                                        # Scale to 10-90 range to leave room for start/end updates
                                        scaled_progress = 10 + int(progress_percent * 0.8)
                                        
                                        await safe_send_progress_update(
                                            job_id,
                                            scaled_progress, 
                                            "processing",
                                            f"Generating image: {progress_percent}% complete, ETA: {eta:.1f}s"
                                        )
                                    
                                    # If generation is complete, stop polling
                                    # [2025-05-20T12:02:05-04:00] Stop polling when job is completed
                                    # This prevents the final 10% progress update from being sent after job completion
                                    if progress_data_dict.get('completed', False):
                                        logger.debug(f"[a1111_connector.py poll_progress] A1111 job completed, stopping progress polling")
                                        return  # Exit the polling function completely instead of just breaking the loop
                        except Exception as e:
                            logger.error(f"[a1111_connector.py poll_progress] Error polling progress: {str(e)}")
                            # We don't send an update here - if there's a real problem, the main request will time out
                            # which is the correct behavior
                        
                        # Wait before polling again (1 second)
                        await asyncio.sleep(1.0)
                except Exception as e:
                    logger.error(f"[a1111_connector.py poll_progress] Error in progress polling: {str(e)}")
            
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
                    await safe_send_progress_update(job_id, 50, "processing", f"Received response from A1111 API in {elapsed_time:.2f}s")
                    
                    # Check response status
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"[a1111_connector.py process_job] Error response from A1111 API: {response.status} - {error_text}")
                        await safe_send_progress_update(job_id, 100, "error", f"A1111 API error: {response.status}")
                        return {
                            "status": "failed",
                            "error": f"A1111 API returned status {response.status}: {error_text}"
                        }
                    
                    # Parse response with timeout
                    # Updated: 2025-04-17T14:11:00-04:00 - Added timeout for response parsing
                    result = await asyncio.wait_for(response.json(), timeout=self.connection_timeout)                    
                    # Send completion update
                    await safe_send_progress_update(job_id, 100, "completed", "Job completed successfully")
                    
                    return {
                        "status": "success",
                        "output": result
                    }
                    
            except asyncio.TimeoutError:
                # Updated: 2025-04-17T14:11:00-04:00 - Improved timeout error handling
                logger.error(f"[a1111_connector.py process_job] Request timed out after {self.connection_timeout} seconds")
                await safe_send_progress_update(job_id, 100, "error", f"Request timed out after {self.connection_timeout} seconds")
                return {
                    "status": "failed",
                    "error": f"Request timed out after {self.connection_timeout} seconds"
                }
                
        except asyncio.TimeoutError:
            # This handles the outer timeout
            logger.error(f"[a1111_connector.py process_job] Request timed out after {self.connection_timeout} seconds")
            await safe_send_progress_update(job_id, 100, "error", f"Request timed out after {self.connection_timeout} seconds")
            return {
                "status": "failed",
                "error": f"Request timed out after {self.connection_timeout} seconds"
            }
        except aiohttp.ClientConnectorError as e:
            # Updated: 2025-04-17T14:12:00-04:00 - Added specific handling for connection errors
            error_msg = f"Connection error to A1111 API at {self.base_url}: {str(e)}"
            logger.error(f"[a1111_connector.py process_job] {error_msg}")
            await safe_send_progress_update(job_id, 100, "error", error_msg)
            return {
                "status": "failed",
                "error": error_msg
            }
        except Exception as e:
            logger.error(f"[a1111_connector.py process_job] Error processing job {job_id}: {str(e)}")
            await safe_send_progress_update(job_id, 100, "error", str(e))
            return {
                "status": "failed",
                "error": str(e)
            }
        finally:
            # Updated: 2025-04-17T14:12:00-04:00 - Always clear current job ID
            # [2025-05-20T12:02:05-04:00] Added proper cleanup of progress polling task
            self.current_job_id = None
            
            # Cancel the progress polling task if it exists
            if progress_polling_task is not None and not progress_polling_task.done():
                progress_polling_task.cancel()
                
                # Wait for the task to be properly canceled
                try:
                    # Use a short timeout to avoid blocking
                    await asyncio.wait_for(progress_polling_task, timeout=0.5)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    # This is expected when canceling the task
                    pass
                except Exception as e:
                    logger.error(f"[a1111_connector.py process_job] Error while canceling progress polling task: {str(e)}")