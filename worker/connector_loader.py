#!/usr/bin/env python3
# Connector loader for the EmProps Redis Worker
import os
import sys
import importlib
import importlib.util
from typing import Dict, List, Any, Type

# Add the parent directory to the Python path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

# Add the current directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Import required modules
from connector_interface import ConnectorInterface
from core.utils.logger import logger

async def load_connectors() -> Dict[str, ConnectorInterface]:
    """Load connectors based on the CONNECTORS environment variable
    
    Returns:
        Dict[str, ConnectorInterface]: Dictionary of connector instances by job type
    """
    # Get connector list from environment variable
    connector_env = os.environ.get("CONNECTORS", "simulation")
    logger.info(f"[connector_loader.py load_connectors()] CONNECTORS environment variable: '{connector_env}'")
    
    connector_list = connector_env.split(",")
    connector_list = [c.strip() for c in connector_list if c.strip()]
    
    # Log Python path for debugging
    logger.info(f"[connector_loader.py load_connectors()] Python path: {sys.path}")
    logger.info(f"[connector_loader.py load_connectors()] Current directory: {os.getcwd()}")
    logger.info(f"[connector_loader.py load_connectors()] Loading connectors: {connector_list}")
    
    # Dictionary to store connector instances by job type
    connectors = {}
    
    # Create connectors directory if it doesn't exist
    os.makedirs("connectors", exist_ok=True)
    
    # Load each connector
    for connector_name in connector_list:
        try:
            # Try to import the connector module
            module_name = f"connectors.{connector_name}_connector"
            logger.info(f"[connector_loader.py load_connectors()] Attempting to import module: {module_name}")
            
            try:
                module = importlib.import_module(module_name)
                logger.info(f"[connector_loader.py load_connectors()] Successfully imported module: {module_name}")
            except ImportError as e:
                # Try with worker.connectors prefix
                alt_module_name = f"worker.connectors.{connector_name}_connector"
                logger.info(f"[connector_loader.py load_connectors()] Import failed: {str(e)}")
                logger.info(f"[connector_loader.py load_connectors()] Trying alternate module path: {alt_module_name}")
                module = importlib.import_module(alt_module_name)
                logger.info(f"[connector_loader.py load_connectors()] Successfully imported module: {alt_module_name}")
            
            # Find the connector class
            logger.info(f"[connector_loader.py load_connectors()] Looking for connector class in module: {module.__name__}")
            connector_class = None
            
            # Log all classes in the module
            all_classes = [name for name in dir(module) if isinstance(getattr(module, name), type)]
            logger.info(f"[connector_loader.py load_connectors()] All classes in module: {all_classes}")
            
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type):
                    logger.info(f"[connector_loader.py load_connectors()] Checking class: {attr_name}, base classes: {attr.__bases__ if hasattr(attr, '__bases__') else 'None'}")
                    
                    try:
                        if (issubclass(attr, ConnectorInterface) and attr != ConnectorInterface):
                            connector_class = attr
                            logger.info(f"[connector_loader.py load_connectors()] Found connector class: {attr_name}")
                            break
                    except TypeError:
                        # This happens when attr is not a class
                        logger.info(f"[connector_loader.py load_connectors()] TypeError checking issubclass for {attr_name}")
            
            if connector_class is None:
                logger.error(f"Could not find connector class in {module_name}")
                continue
            
            # Create connector instance
            connector = connector_class()
            
            # Initialize connector
            success = await connector.initialize() #### THIS IS WHERE CONNECTORS ARE INITIALIZED
            if not success:
                logger.error(f"Failed to initialize connector: {connector_name}")
                continue
            
            # Get job type from connector
            job_type = connector.get_job_type()
            
            # Add connector to dictionary
            connectors[job_type] = connector #### THIS IS WHERE CONNECTORS ARE ADDED TO THE DICTIONARY
            logger.info(f"Loaded connector: {connector_name} for job type: {job_type}")
        
        except Exception as e:
            logger.error(f"Error loading connector {connector_name}: {str(e)}")
    
    return connectors #### THIS IS WHERE CONNECTOR DICTIONARY IS RETURNED

def get_supported_job_types(connectors: Dict[str, ConnectorInterface]) -> List[str]:
    """Get list of supported job types from loaded connectors
    
    Args:
        connectors: Dictionary of connector instances by job type
        
    Returns:
        List[str]: List of supported job types
    """
    return list(connectors.keys())

async def get_worker_capabilities(connectors: Dict[str, ConnectorInterface]) -> Dict[str, Any]:
    """Get worker capabilities based on loaded connectors
    
    Args:
        connectors: Dictionary of connector instances by job type
        
    Returns:
        Dict[str, Any]: Worker capabilities dictionary
    """
    # Log the connectors being used to build capabilities
    logger.info(f"[connector_loader.py get_worker_capabilities()] Building worker capabilities with connectors: {list(connectors.keys())}")
    
    # Get supported job types
    supported_job_types = get_supported_job_types(connectors)
    logger.info(f"[connector_loader.py get_worker_capabilities()] Supported job types from connectors: {supported_job_types}")
    
    # Base capabilities
    capabilities = {
        "version": "1.0.0",
        "supported_job_types": supported_job_types,
        "cpu": True,
        "memory": "16GB",
    }
    
    # Add connector-specific capabilities
    for job_type, connector in connectors.items():
        logger.info(f"[connector_loader.py get_worker_capabilities()] Getting capabilities for connector: {job_type}")
        connector_capabilities = connector.get_capabilities()
        logger.info(f"[connector_loader.py get_worker_capabilities()] Connector {job_type} capabilities: {connector_capabilities}")
        
        for key, value in connector_capabilities.items():
            # Add connector prefix to avoid conflicts
            capabilities[f"{job_type}_{key}"] = value
    
    # Log the final capabilities
    logger.info(f"[connector_loader.py get_worker_capabilities()] Final worker capabilities: {capabilities}")
    
    return capabilities
