#!/usr/bin/env python3
# Connector loader for the EmProps Redis Worker
import os
import importlib
import importlib.util
from typing import Dict, List, Any, Type

# Setup imports
from setup_imports import setup_imports
setup_imports()

# Import required modules
from connector_interface import ConnectorInterface
from core.utils.logger import logger

def load_connectors() -> Dict[str, ConnectorInterface]:
    """Load connectors based on the CONNECTORS environment variable
    
    Returns:
        Dict[str, ConnectorInterface]: Dictionary of connector instances by job type
    """
    # Get connector list from environment variable
    connector_list = os.environ.get("CONNECTORS", "simulation").split(",")
    connector_list = [c.strip() for c in connector_list if c.strip()]
    
    logger.info(f"Loading connectors: {connector_list}")
    
    # Dictionary to store connector instances by job type
    connectors = {}
    
    # Create connectors directory if it doesn't exist
    os.makedirs("connectors", exist_ok=True)
    
    # Load each connector
    for connector_name in connector_list:
        try:
            # Try to import the connector module
            module_name = f"connectors.{connector_name}_connector"
            module = importlib.import_module(module_name)
            
            # Find the connector class
            connector_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, ConnectorInterface) and 
                    attr != ConnectorInterface):
                    connector_class = attr
                    break
            
            if connector_class is None:
                logger.error(f"Could not find connector class in {module_name}")
                continue
            
            # Create connector instance
            connector = connector_class()
            
            # Initialize connector
            success = connector.initialize()
            if not success:
                logger.error(f"Failed to initialize connector: {connector_name}")
                continue
            
            # Get job type from connector
            job_type = connector.get_job_type()
            
            # Add connector to dictionary
            connectors[job_type] = connector
            logger.info(f"Loaded connector: {connector_name} for job type: {job_type}")
        
        except Exception as e:
            logger.error(f"Error loading connector {connector_name}: {str(e)}")
    
    return connectors

def get_supported_job_types(connectors: Dict[str, ConnectorInterface]) -> List[str]:
    """Get list of supported job types from loaded connectors
    
    Args:
        connectors: Dictionary of connector instances by job type
        
    Returns:
        List[str]: List of supported job types
    """
    return list(connectors.keys())

def get_worker_capabilities(connectors: Dict[str, ConnectorInterface]) -> Dict[str, Any]:
    """Get worker capabilities based on loaded connectors
    
    Args:
        connectors: Dictionary of connector instances by job type
        
    Returns:
        Dict[str, Any]: Worker capabilities dictionary
    """
    # Base capabilities
    capabilities = {
        "version": "1.0.0",
        "supported_job_types": get_supported_job_types(connectors),
        "cpu": True,
        "memory": "16GB",
    }
    
    # Add connector-specific capabilities
    for job_type, connector in connectors.items():
        connector_capabilities = connector.get_capabilities()
        for key, value in connector_capabilities.items():
            # Add connector prefix to avoid conflicts
            capabilities[f"{job_type}_{key}"] = value
    
    return capabilities
