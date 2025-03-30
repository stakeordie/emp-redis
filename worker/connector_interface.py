#!/usr/bin/env python3
# Connector interface for the EmProps Redis Worker
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Union

class ConnectorInterface(ABC):
    """Interface for service connectors that handle specific job types"""
    
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
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """Clean up resources when worker is shutting down"""
        pass
