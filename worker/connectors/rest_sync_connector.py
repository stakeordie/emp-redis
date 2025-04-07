#!/usr/bin/env python3
# REST Synchronous connector for the EmProps Redis Worker
# Created: 2025-04-06T21:10:38-04:00
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
    from worker.connector_interface import ConnectorInterface
except ImportError:
    # Fall back to package imports (for local development)
    from ..connector_interface import ConnectorInterface
from core.utils.logger import logger

class RESTSyncConnector(ConnectorInterface):
    """Connector for synchronous REST API calls"""
    
    # Version identifier to verify code deployment
    VERSION = "2025-04-06-21:10-initial-implementation"
    
    def __init__(self):
        """Initialize the REST synchronous connector"""
        # REST API connection settings (support both namespaced and non-namespaced)
        self.base_url = os.environ.get("WORKER_REST_BASE_URL", os.environ.get("REST_BASE_URL", "http://localhost:8000"))
        self.endpoint = os.environ.get("WORKER_REST_ENDPOINT", os.environ.get("REST_ENDPOINT", "/api/process"))
        self.use_ssl = os.environ.get("WORKER_REST_USE_SSL", os.environ.get("REST_USE_SSL", "false")).lower() in ("true", "1", "yes")
        self.timeout = int(os.environ.get("WORKER_REST_TIMEOUT", os.environ.get("REST_TIMEOUT", "60")))
        self.job_type = os.environ.get("WORKER_REST_JOB_TYPE", os.environ.get("REST_JOB_TYPE", "rest"))
        
        # Authentication settings
        self.api_key = os.environ.get("WORKER_REST_API_KEY", os.environ.get("REST_API_KEY"))
        self.username = os.environ.get("WORKER_REST_USERNAME", os.environ.get("REST_USERNAME"))
        self.password = os.environ.get("WORKER_REST_PASSWORD", os.environ.get("REST_PASSWORD"))
        
        # Log which variables we're using
        logger.info(f"[rest_sync_connector.py __init__] Using environment variables:")
        logger.info(f"[rest_sync_connector.py __init__] WORKER_REST_BASE_URL/REST_BASE_URL: {self.base_url}")
        logger.info(f"[rest_sync_connector.py __init__] WORKER_REST_ENDPOINT/REST_ENDPOINT: {self.endpoint}")
        logger.info(f"[rest_sync_connector.py __init__] WORKER_REST_USE_SSL/REST_USE_SSL: {self.use_ssl}")
        logger.info(f"[rest_sync_connector.py __init__] WORKER_REST_TIMEOUT/REST_TIMEOUT: {self.timeout}")
        logger.info(f"[rest_sync_connector.py __init__] WORKER_REST_JOB_TYPE/REST_JOB_TYPE: {self.job_type}")
        
        # Connection status
        self.session = None
        self.connection_details = {
            "base_url": self.base_url,
            "endpoint": self.endpoint,
            "use_ssl": self.use_ssl,
            "timeout": self.timeout
        }
        
        # Job tracking
        self.current_job_id = None
    
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
            health_endpoint = os.environ.get("WORKER_REST_HEALTH_ENDPOINT", os.environ.get("REST_HEALTH_ENDPOINT", "/health"))
            if health_endpoint:
                try:
                    url = f"{self.base_url}{health_endpoint}"
                    async with self.session.get(url, headers=self._get_headers()) as response:
                        if response.status == 200:
                            logger.info(f"[rest_sync_connector.py initialize] Successfully connected to REST API at {url}")
                        else:
                            logger.warning(f"[rest_sync_connector.py initialize] Health check failed with status {response.status}")
                except Exception as e:
                    logger.warning(f"[rest_sync_connector.py initialize] Health check failed: {str(e)}")
            
            logger.info(f"[rest_sync_connector.py initialize] REST sync connector initialized with URL: {self.base_url}{self.endpoint}")
            return True
        except Exception as e:
            logger.error(f"[rest_sync_connector.py initialize] Initialization error: {str(e)}")
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
            "rest_sync_version": self.VERSION,
            "supports_synchronous": True,
            "timeout": self.timeout
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
            logger.info(f"[rest_sync_connector.py process_job] Processing job {job_id}")
            
            # Create session if it doesn't exist
            if self.session is None:
                self.session = aiohttp.ClientSession()
            
            # Send initial progress update
            await send_progress_update(job_id, 0, "started", f"Starting {self.get_job_type()} job")
            
            # Prepare request data
            request_data = {
                "job_id": job_id,
                **payload
            }
            
            # Send request to REST API
            url = f"{self.base_url}{self.endpoint}"
            logger.info(f"[rest_sync_connector.py process_job] Sending request to {url}")
            await send_progress_update(job_id, 10, "processing", f"Sending request to REST API")
            
            start_time = time.time()
            async with self.session.post(
                url,
                headers=self._get_headers(),
                json=request_data,
                timeout=self.timeout
            ) as response:
                elapsed_time = time.time() - start_time
                
                # Send progress update
                await send_progress_update(job_id, 50, "processing", f"Received response from REST API in {elapsed_time:.2f}s")
                
                # Check response status
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"[rest_sync_connector.py process_job] Error response from REST API: {response.status} - {error_text}")
                    await send_progress_update(job_id, 100, "error", f"REST API error: {response.status}")
                    return {
                        "status": "failed",
                        "error": f"REST API returned status {response.status}: {error_text}"
                    }
                
                # Parse response
                result = await response.json()
                logger.info(f"[rest_sync_connector.py process_job] Received successful response from REST API")
                
                # Send completion update
                await send_progress_update(job_id, 100, "completed", "Job completed successfully")
                
                return {
                    "status": "success",
                    "output": result
                }
        except asyncio.TimeoutError:
            logger.error(f"[rest_sync_connector.py process_job] Request timed out after {self.timeout} seconds")
            await send_progress_update(job_id, 100, "error", f"Request timed out after {self.timeout} seconds")
            return {
                "status": "failed",
                "error": f"Request timed out after {self.timeout} seconds"
            }
        except Exception as e:
            logger.error(f"[rest_sync_connector.py process_job] Error processing job {job_id}: {str(e)}")
            await send_progress_update(job_id, 100, "error", str(e))
            return {
                "status": "failed",
                "error": str(e)
            }
        finally:
            # Clear current job ID when done
            logger.info(f"[rest_sync_connector.py process_job] Completed job {job_id}")
            self.current_job_id = None
    
    async def shutdown(self) -> None:
        """Clean up resources when worker is shutting down"""
        logger.info(f"[rest_sync_connector.py shutdown] Shutting down REST sync connector")
        if self.session:
            await self.session.close()
            self.session = None
        logger.info(f"[rest_sync_connector.py shutdown] REST sync connector shut down")
