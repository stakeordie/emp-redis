#!/usr/bin/env python3
# REST Asynchronous connector for the EmProps Redis Worker
# Created: 2025-04-06T21:10:38-04:00
import sys
import os

# Add the parent directory to the Python path
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, parent_dir)

# Add the worker directory to the Python path
worker_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, worker_dir)
import json
import asyncio
import aiohttp
import time
from typing import Dict, Any, Optional, Union, Callable

# Try direct imports first (for Docker container)
try:
    from worker.connector_interface import ConnectorInterface
except ImportError:
    # Fall back to package imports (for local development)
    from ..connector_interface import ConnectorInterface
from core.utils.logger import logger
from abc import ABC, abstractmethod

class RESTAsyncConnector(ConnectorInterface, ABC):
    """Connector for asynchronous REST API calls with polling
    
    This base class handles the common patterns for asynchronous REST API calls:
    1. Submit a job to an endpoint and get a job ID
    2. Poll a status endpoint to check job progress
    3. Retrieve results from a result endpoint when the job is complete
    
    Implementing classes should override the following methods:
    - get_submit_endpoint() - Return the endpoint for job submission
    - get_status_endpoint(job_id) - Return the endpoint for checking job status
    - get_result_endpoint(job_id) - Return the endpoint for retrieving results
    - parse_job_id_from_response(response) - Extract job ID from submission response
    - parse_status_from_response(response) - Extract status from status response
    - parse_result_from_response(response) - Extract result from result response
    """
    
    # Version identifier to verify code deployment
    VERSION = "2025-04-06-21:10-initial-implementation"
    
    def __init__(self):
        """Initialize the REST asynchronous connector"""
        # REST API connection settings (support both namespaced and non-namespaced)
        self.base_url = os.environ.get("WORKER_REST_ASYNC_BASE_URL", os.environ.get("REST_ASYNC_BASE_URL", "http://localhost:8000"))
        self.submit_endpoint = os.environ.get("WORKER_REST_ASYNC_SUBMIT_ENDPOINT", os.environ.get("REST_ASYNC_SUBMIT_ENDPOINT", "/api/submit"))
        self.status_endpoint = os.environ.get("WORKER_REST_ASYNC_STATUS_ENDPOINT", os.environ.get("REST_ASYNC_STATUS_ENDPOINT", "/api/status"))
        self.result_endpoint = os.environ.get("WORKER_REST_ASYNC_RESULT_ENDPOINT", os.environ.get("REST_ASYNC_RESULT_ENDPOINT", "/api/result"))
        self.use_ssl = os.environ.get("WORKER_REST_ASYNC_USE_SSL", os.environ.get("REST_ASYNC_USE_SSL", "false")).lower() in ("true", "1", "yes")
        self.timeout = int(os.environ.get("WORKER_REST_ASYNC_TIMEOUT", os.environ.get("REST_ASYNC_TIMEOUT", "300")))  # 5 minutes default
        self.poll_interval = float(os.environ.get("WORKER_REST_ASYNC_POLL_INTERVAL", os.environ.get("REST_ASYNC_POLL_INTERVAL", "2.0")))  # 2 seconds default
        self.job_type = os.environ.get("WORKER_REST_ASYNC_JOB_TYPE", os.environ.get("REST_ASYNC_JOB_TYPE", "rest_async"))
        
        # Authentication settings
        self.api_key = os.environ.get("WORKER_REST_ASYNC_API_KEY", os.environ.get("REST_ASYNC_API_KEY"))
        self.username = os.environ.get("WORKER_REST_ASYNC_USERNAME", os.environ.get("REST_ASYNC_USERNAME"))
        self.password = os.environ.get("WORKER_REST_ASYNC_PASSWORD", os.environ.get("REST_ASYNC_PASSWORD"))
        
        # Log which variables we're using
        logger.info(f"[rest_async_connector.py __init__] Using environment variables:")
        logger.info(f"[rest_async_connector.py __init__] WORKER_REST_ASYNC_BASE_URL/REST_ASYNC_BASE_URL: {self.base_url}")
        logger.info(f"[rest_async_connector.py __init__] WORKER_REST_ASYNC_SUBMIT_ENDPOINT/REST_ASYNC_SUBMIT_ENDPOINT: {self.submit_endpoint}")
        logger.info(f"[rest_async_connector.py __init__] WORKER_REST_ASYNC_STATUS_ENDPOINT/REST_ASYNC_STATUS_ENDPOINT: {self.status_endpoint}")
        logger.info(f"[rest_async_connector.py __init__] WORKER_REST_ASYNC_RESULT_ENDPOINT/REST_ASYNC_RESULT_ENDPOINT: {self.result_endpoint}")
        logger.info(f"[rest_async_connector.py __init__] WORKER_REST_ASYNC_USE_SSL/REST_ASYNC_USE_SSL: {self.use_ssl}")
        logger.info(f"[rest_async_connector.py __init__] WORKER_REST_ASYNC_TIMEOUT/REST_ASYNC_TIMEOUT: {self.timeout}")
        logger.info(f"[rest_async_connector.py __init__] WORKER_REST_ASYNC_POLL_INTERVAL/REST_ASYNC_POLL_INTERVAL: {self.poll_interval}")
        logger.info(f"[rest_async_connector.py __init__] WORKER_REST_ASYNC_JOB_TYPE/REST_ASYNC_JOB_TYPE: {self.job_type}")
        
        # Connection status
        self.session = None
        self.connection_details = {
            "base_url": self.base_url,
            "submit_endpoint": self.submit_endpoint,
            "status_endpoint": self.status_endpoint,
            "result_endpoint": self.result_endpoint,
            "use_ssl": self.use_ssl,
            "timeout": self.timeout,
            "poll_interval": self.poll_interval
        }
        
        # Job tracking
        self.current_job_id = None
        self.external_job_id = None
    
    async def initialize(self) -> bool:
        """Initialize the connector
        
        Returns:
            bool: True if initialization was successful, False otherwise
        """
        try:
            # Create HTTP session
            self.session = aiohttp.ClientSession()
            
            # Test connection by making a simple request (if an endpoint is available for this)
            # This is optional and depends on the API having a health check endpoint
            health_endpoint = os.environ.get("WORKER_REST_ASYNC_HEALTH_ENDPOINT", os.environ.get("REST_ASYNC_HEALTH_ENDPOINT", "/health"))
            if health_endpoint:
                try:
                    url = f"{self.base_url}{health_endpoint}"
                    async with self.session.get(url, headers=self._get_headers()) as response:
                        if response.status == 200:
                            logger.info(f"[rest_async_connector.py initialize] Successfully connected to REST API at {url}")
                        else:
                            logger.warning(f"[rest_async_connector.py initialize] Health check failed with status {response.status}")
                except Exception as e:
                    logger.warning(f"[rest_async_connector.py initialize] Health check failed: {str(e)}")
            
            logger.info(f"[rest_async_connector.py initialize] REST async connector initialized with URL: {self.base_url}")
            return True
        except Exception as e:
            logger.error(f"[rest_async_connector.py initialize] Initialization error: {str(e)}")
            return False
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for REST API requests
        
        Returns:
            Dict[str, str]: Headers for REST API requests
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Add authentication if provided
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        elif self.username and self.password:
            import base64
            credentials = f"{self.username}:{self.password}"
            encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
            headers["Authorization"] = f"Basic {encoded_credentials}"
            
        return headers
    
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
            "rest_async_version": self.VERSION,
            "supports_asynchronous": True,
            "timeout": self.timeout,
            "poll_interval": self.poll_interval
        }
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get the current connection status of the connector
        
        Returns:
            Dict[str, Any]: Connection status information
        """
        return {
            "connected": self.session is not None,
            "service": self.get_job_type(),
            "details": self.connection_details,
            "current_job_id": self.current_job_id,
            "external_job_id": self.external_job_id,
            "version": self.VERSION
        }
    
    def is_processing_job(self, job_id: str) -> bool:
        """Check if this connector is currently processing the specified job
        
        Args:
            job_id (str): The ID of the job to check
            
        Returns:
            bool: True if this connector is processing the job, False otherwise
        """
        return self.current_job_id == job_id
    
    @abstractmethod
    def get_submit_endpoint(self) -> str:
        """Return the endpoint for job submission
        
        This method should be overridden by implementing classes to return
        the endpoint for job submission. The endpoint should be a string
        that will be appended to the base URL.
        
        Returns:
            str: The endpoint for job submission
        """
        return os.environ.get(
            f"WORKER_{self.job_type.upper()}_SUBMIT_ENDPOINT",
            os.environ.get(
                f"{self.job_type.upper()}_SUBMIT_ENDPOINT",
                "/api/submit"
            )
        )
    
    @abstractmethod
    def get_status_endpoint(self, job_id: str) -> str:
        """Return the endpoint for checking job status
        
        This method should be overridden by implementing classes to return
        the endpoint for checking job status. The endpoint should be a string
        that will be appended to the base URL.
        
        Args:
            job_id (str): The job ID to check status for
            
        Returns:
            str: The endpoint for checking job status
        """
        return self.status_endpoint.replace("{job_id}", job_id)
    
    @abstractmethod
    def get_result_endpoint(self, job_id: str) -> str:
        """Return the endpoint for retrieving results
        
        This method should be overridden by implementing classes to return
        the endpoint for retrieving results. The endpoint should be a string
        that will be appended to the base URL.
        
        Args:
            job_id (str): The job ID to retrieve results for
            
        Returns:
            str: The endpoint for retrieving results
        """
        endpoint_template = os.environ.get(
            f"WORKER_{self.job_type.upper()}_RESULT_ENDPOINT",
            os.environ.get(
                f"{self.job_type.upper()}_RESULT_ENDPOINT",
                "/api/result/{job_id}"
            )
        )
        return endpoint_template.format(job_id=job_id)
    
    @abstractmethod
    def parse_job_id_from_response(self, response: Dict[str, Any]) -> Optional[str]:
        """Extract job ID from submission response
        
        This method should be overridden by implementing classes to extract
        the job ID from the submission response.
        
        Args:
            response (Dict[str, Any]): The response from the submit endpoint
            
        Returns:
            Optional[str]: The external job ID if found, None otherwise
        """
        return response.get("job_id")
    
    @abstractmethod
    def parse_status_from_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract status from status response
        
        This method should be overridden by implementing classes to extract
        the status from the status response. The status will be used to
        determine if the job is complete.
        
        Args:
            response (Dict[str, Any]): The response from the status endpoint
            
        Returns:
            Dict[str, Any]: The status information
        """
        # Default implementation assumes the response is the status
        return response
    
    @abstractmethod
    def parse_result_from_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract result from result response
        
        This method should be overridden by implementing classes to extract
        the result from the result response.
        
        Args:
            response (Dict[str, Any]): The response from the result endpoint
            
        Returns:
            Dict[str, Any]: The result information
        """
        return response
    
    async def submit_job(self, job_id: str, payload: Dict[str, Any]) -> Optional[str]:
        """Submit a job to the REST API
        
        Args:
            job_id (str): The ID of the job
            payload (Dict[str, Any]): The job payload
            
        Returns:
            Optional[str]: The external job ID if successful, None otherwise
        """
        # Prepare request data
        request_data = {
            "job_id": job_id,
            **payload
        }
        
        # Send request to REST API
        url = f"{self.base_url}{self.get_submit_endpoint()}"
        logger.info(f"[rest_async_connector.py submit_job] Submitting job to {url}")
        
        try:
            if self.session is None:
                self.session = aiohttp.ClientSession()
                
            async with self.session.post(
                url,
                headers=self._get_headers(),
                json=request_data,
                timeout=30  # Short timeout for submission
            ) as response:
                # Check response status
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"[rest_async_connector.py submit_job] Error response from REST API: {response.status} - {error_text}")
                    return None  # Explicitly return None to match Optional[str] return type
                
                # Parse response
                result = await response.json()
                
                # Extract external job ID
                external_job_id = self.parse_job_id_from_response(result)
                if not external_job_id:
                    logger.error(f"[rest_async_connector.py submit_job] No job_id in response: {result}")
                    return None  # Explicitly return None to match Optional[str] return type
                
                logger.info(f"[rest_async_connector.py submit_job] Job submitted successfully, external job ID: {external_job_id}")
                return external_job_id
        except Exception as e:
            logger.error(f"[rest_async_connector.py submit_job] Error submitting job: {str(e)}")
            return None
    
    async def check_job_status(self, external_job_id: str) -> Dict[str, Any]:
        """Check the status of a job
        
        Args:
            external_job_id (str): The external job ID
            
        Returns:
            Dict[str, Any]: The job status
        """
        url = f"{self.base_url}{self.get_status_endpoint(external_job_id)}"
        logger.debug(f"[rest_async_connector.py check_job_status] Checking job status at {url}")
        
        try:
            if self.session is None:
                self.session = aiohttp.ClientSession()
                
            async with self.session.get(
                url,
                headers=self._get_headers(),
                timeout=10  # Short timeout for status check
            ) as response:
                # Check response status
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"[rest_async_connector.py check_job_status] Error response from REST API: {response.status} - {error_text}")
                    # Explicitly create Dict[str, Any] to satisfy type checker
                    status_result: Dict[str, Any] = {"status": "error", "message": f"API returned status {response.status}: {error_text}"}
                    return status_result
                
                # Parse response
                response_data = await response.json()
                logger.debug(f"[rest_async_connector.py check_job_status] Job status: {response_data}")
                return self.parse_status_from_response(response_data)
        except Exception as e:
            logger.error(f"[rest_async_connector.py check_job_status] Error checking job status: {str(e)}")
            # Explicitly create Dict[str, Any] to satisfy type checker
            error_result: Dict[str, Any] = {"status": "error", "message": str(e)}
            return error_result
    
    async def get_job_result(self, external_job_id: str) -> Dict[str, Any]:
        """Get the result of a completed job
        
        Args:
            external_job_id (str): The external job ID
            
        Returns:
            Dict[str, Any]: The job result
        """
        url = f"{self.base_url}{self.get_result_endpoint(external_job_id)}"
        logger.info(f"[rest_async_connector.py get_job_result] Getting job result from {url}")
        
        try:
            if self.session is None:
                self.session = aiohttp.ClientSession()
                
            async with self.session.get(
                url,
                headers=self._get_headers(),
                timeout=30  # Longer timeout for result retrieval
            ) as response:
                # Check response status
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"[rest_async_connector.py get_job_result] Error response from REST API: {response.status} - {error_text}")
                    # Explicitly create Dict[str, Any] to satisfy type checker
                    status_result: Dict[str, Any] = {"status": "error", "message": f"API returned status {response.status}: {error_text}"}
                    return status_result
                
                # Parse response
                response_data = await response.json()
                logger.info(f"[rest_async_connector.py get_job_result] Job result retrieved successfully")
                return self.parse_result_from_response(response_data)
        except Exception as e:
            logger.error(f"[rest_async_connector.py get_job_result] Error getting job result: {str(e)}")
            # Explicitly create Dict[str, Any] to satisfy type checker
            error_result: Dict[str, Any] = {"status": "error", "message": str(e)}
            return error_result
    
    async def process_job(self, websocket, job_id: str, payload: Dict[str, Any], send_progress_update) -> Dict[str, Any]:
        """Process a job using the REST API
        
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
            logger.info(f"[rest_async_connector.py process_job] Processing job {job_id}")
            
            # Create session if it doesn't exist
            if self.session is None:
                self.session = aiohttp.ClientSession()
            
            # Send initial progress update
            await send_progress_update(job_id, 0, "started", f"Starting {self.get_job_type()} job")
            
            # Submit job to REST API
            await send_progress_update(job_id, 5, "submitting", "Submitting job to REST API")
            external_job_id = await self.submit_job(job_id, payload)
            if not external_job_id:
                await send_progress_update(job_id, 100, "error", "Failed to submit job to REST API")
                return {
                    "status": "failed",
                    "error": "Failed to submit job to REST API"
                }
            
            # Store external job ID
            self.external_job_id = external_job_id
            await send_progress_update(job_id, 10, "submitted", f"Job submitted to REST API, external job ID: {external_job_id}")
            
            # Poll for job completion
            start_time = time.time()
            last_progress = 10
            last_status_message = ""
            
            while True:
                # Check if we've exceeded the timeout
                elapsed_time = time.time() - start_time
                if elapsed_time > self.timeout:
                    logger.error(f"[rest_async_connector.py process_job] Job timed out after {self.timeout} seconds")
                    await send_progress_update(job_id, 100, "error", f"Job timed out after {self.timeout} seconds")
                    return {
                        "status": "failed",
                        "error": f"Job timed out after {self.timeout} seconds"
                    }
                
                # Check job status
                status_result = await self.check_job_status(external_job_id)
                status = status_result.get("status", "unknown")
                
                # Handle different status values
                if status == "completed":
                    logger.info(f"[rest_async_connector.py process_job] Job completed")
                    await send_progress_update(job_id, 90, "finalizing", "Job completed, retrieving results")
                    break
                elif status == "failed":
                    error_message = status_result.get("message", "Unknown error")
                    logger.error(f"[rest_async_connector.py process_job] Job failed: {error_message}")
                    await send_progress_update(job_id, 100, "error", f"Job failed: {error_message}")
                    return {
                        "status": "failed",
                        "error": error_message
                    }
                elif status == "processing":
                    # Update progress if available
                    progress = status_result.get("progress", -1)
                    if progress >= 0:
                        # Scale progress to 10-90%
                        scaled_progress = 10 + int(progress * 0.8)
                        if scaled_progress != last_progress:
                            last_progress = scaled_progress
                            status_message = status_result.get("message", f"Processing: {progress}%")
                            await send_progress_update(job_id, scaled_progress, "processing", status_message)
                            last_status_message = status_message
                    elif last_status_message != status_result.get("message", ""):
                        # If no progress but new message, update with the message
                        status_message = status_result.get("message", "Processing")
                        await send_progress_update(job_id, last_progress, "processing", status_message)
                        last_status_message = status_message
                    
                    # Send heartbeat every 5 polling intervals
                    if int(elapsed_time / self.poll_interval) % 5 == 0:
                        await send_progress_update(job_id, -1, "heartbeat", f"Job processing, elapsed time: {elapsed_time:.1f}s")
                else:
                    # Unknown status, just wait
                    logger.info(f"[rest_async_connector.py process_job] Job status: {status}")
                
                # Wait before polling again
                await asyncio.sleep(self.poll_interval)
            
            # Get job result
            result = await self.get_job_result(external_job_id)
            
            # Check if result contains an error
            if result.get("status") == "error":
                error_message = result.get("message", "Unknown error")
                logger.error(f"[rest_async_connector.py process_job] Error getting job result: {error_message}")
                await send_progress_update(job_id, 100, "error", f"Error getting job result: {error_message}")
                return {
                    "status": "failed",
                    "error": error_message
                }
            
            # Send completion update
            await send_progress_update(job_id, 100, "completed", "Job completed successfully")
            
            return {
                "status": "success",
                "output": result
            }
        except Exception as e:
            logger.error(f"[rest_async_connector.py process_job] Error processing job {job_id}: {str(e)}")
            await send_progress_update(job_id, 100, "error", str(e))
            return {
                "status": "failed",
                "error": str(e)
            }
        finally:
            # Clear tracking variables
            logger.info(f"[rest_async_connector.py process_job] Completed job {job_id}")
            self.current_job_id = None
            self.external_job_id = None
    
    async def shutdown(self) -> None:
        """Clean up resources when worker is shutting down"""
        logger.info(f"[rest_async_connector.py shutdown] Shutting down REST async connector")
        if self.session:
            await self.session.close()
            self.session = None
        logger.info(f"[rest_async_connector.py shutdown] REST async connector shut down")
