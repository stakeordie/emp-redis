#!/usr/bin/env python3
# Connector interface for the EmProps Redis Worker
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Union

class ConnectorInterface(ABC):
    """Interface for service connectors that handle specific job types"""
    
    # Class attribute to identify the connector type
    # This should be overridden by each connector implementation
    # and should match the name used in the WORKER_CONNECTORS environment variable
    # Updated: 2025-04-07T15:48:00-04:00
    # [2025-05-25T21:05:00-04:00] Changed connector_name type to Optional[str] to allow string values in subclasses
    connector_name: Optional[str] = None
    
    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the connector
        
        Returns:
            bool: True if initialization was successful, False otherwise
        """
        pass
    
    @abstractmethod
    def get_job_type(self) -> str:
        """Get the job type that this connector handles
        
        Returns:
            str: The job type string (e.g., "comfyui")
        """
        pass
    
    @abstractmethod
    def get_capabilities(self) -> Dict[str, Any]:
        """Get connector-specific capabilities
        
        Returns:
            Dict[str, Any]: Capabilities dictionary to be merged with worker capabilities
        """
        pass
    
    @abstractmethod
    def get_connection_status(self) -> Dict[str, Any]:
        """Get the current connection status of the connector
        
        Returns:
            Dict[str, Any]: Connection status information including:
                - connected (bool): Whether the connector is currently connected
                - service (str): The name of the service (e.g., "comfyui")
                - details (Dict[str, Any]): Additional service-specific details
        """
        pass
    
    @abstractmethod
    def is_processing_job(self, job_id: str) -> bool:
        """Check if this connector is currently processing the specified job
        
        Args:
            job_id (str): The ID of the job to check
            
        Returns:
            bool: True if this connector is processing the job, False otherwise
        """
        pass
    
    @abstractmethod
    async def process_job(self, websocket, job_id: str, payload: Dict[str, Any], send_progress_update) -> Dict[str, Any]:
        """Process a job
        
        For connectors that use websockets to external services, this method should:
        1. Open a new websocket connection at the beginning of job processing
        2. Process the job using that connection
        3. Close the websocket connection when the job is complete (in a finally block)
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
            job_id: The ID of the job to process
            payload: The job payload
            send_progress_update: Function to send progress updates
            
        Returns:
            Dict[str, Any]: Job result
        """
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """Clean up resources when worker is shutting down"""
        pass
        
    async def monitor_ws_connection(self, websocket, worker_id: str) -> None:
        """Monitor WebSocket connection to external service and send status updates
        
        This method is optional and only needs to be implemented by connectors
        that use WebSockets to connect to external services.
        
        Args:
            websocket: The WebSocket connection to the Redis Hub
            worker_id: The ID of the worker
        """
        # Default implementation does nothing
        pass
