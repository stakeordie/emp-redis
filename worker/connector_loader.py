#!/usr/bin/env python3
# Connector loader for the EmProps Redis Worker
# Updated: 2025-04-07T11:39:00-04:00 - Added diagnostic information

import os
import sys
import importlib
import importlib.util
import inspect
import glob
from typing import Dict, List, Any, Type

# Print diagnostic information about the environment
def print_diagnostic_info():
    """Print diagnostic information about the Python environment"""
    logger.info("===== DIAGNOSTIC INFORMATION =====")
    logger.info(f"Current working directory: {os.getcwd()}")
    logger.info(f"__file__: {__file__}")
    logger.info(f"Directory of this file: {os.path.dirname(os.path.abspath(__file__))}")
    
    # Print Python path
    logger.info("Python sys.path:")
    for i, path in enumerate(sys.path):
        logger.info(f"  {i}: {path}")
    
    # Check if worker is a package
    logger.info(f"Is 'worker' a package? {os.path.isdir('worker') and os.path.exists(os.path.join('worker', '__init__.py'))}")
    
    # List directories in current path
    logger.info("Directories in current path:")
    for item in os.listdir(os.getcwd()):
        if os.path.isdir(item):
            logger.info(f"  {item}/")
            # Check if it has __init__.py
            init_path = os.path.join(item, '__init__.py')
            logger.info(f"    Has __init__.py: {os.path.exists(init_path)}")
    
    # Check emp-redis-worker structure if it exists
    emp_redis_path = '/app/emp-redis-worker'
    if os.path.exists(emp_redis_path):
        logger.info(f"emp-redis-worker exists at {emp_redis_path}")
        logger.info("Contents:")
        for item in os.listdir(emp_redis_path):
            logger.info(f"  {item}")
    
    logger.info("=================================")

# Import logger first so we can use it in the import block
from core.utils.logger import logger

# Define ConnectorInterface as a type annotation to avoid lint errors
from typing import Protocol, runtime_checkable

@runtime_checkable
class ConnectorInterface(Protocol):
    """Protocol class for type checking ConnectorInterface"""
    async def initialize(self) -> None: ...
    async def get_capabilities(self) -> Dict[str, Any]: ...
    async def process_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]: ...
    async def shutdown(self) -> None: ...

# Import the actual connector interface
# This works regardless of where the app is located
try:
    # First try relative import (best practice for packages)
    from .connector_interface import ConnectorInterface as ActualConnectorInterface
    logger.info("Successfully imported ConnectorInterface via relative import")
    # Replace our Protocol with the actual implementation
    ConnectorInterface = ActualConnectorInterface
except ImportError as e:
    logger.info(f"Failed to import ConnectorInterface via relative import: {str(e)}")
    # Fall back to direct import if not in a package context
    try:
        from connector_interface import ConnectorInterface as ActualConnectorInterface
        logger.info("Successfully imported ConnectorInterface via direct import")
        # Replace our Protocol with the actual implementation
        ConnectorInterface = ActualConnectorInterface
    except ImportError as e2:
        logger.info(f"Failed to import ConnectorInterface via direct import: {str(e2)}")
        # Try absolute import
        try:
            from worker.connector_interface import ConnectorInterface as ActualConnectorInterface
            logger.info("Successfully imported ConnectorInterface via absolute import")
            # Replace our Protocol with the actual implementation
            ConnectorInterface = ActualConnectorInterface
        except ImportError as e3:
            logger.info(f"Failed to import ConnectorInterface via absolute import: {str(e3)}")
            # Last resort - try to find the file and import it directly
            try:
                # Look in various places
                possible_paths = [
                    os.path.join(os.getcwd(), 'connector_interface.py'),
                    os.path.join(os.getcwd(), 'worker', 'connector_interface.py'),
                    os.path.join(os.path.dirname(__file__), 'connector_interface.py'),
                    '/app/emp-redis-worker/worker/connector_interface.py'
                ]
                
                connector_interface_path = None
                for path in possible_paths:
                    if os.path.exists(path):
                        connector_interface_path = path
                        logger.info(f"Found connector_interface.py at: {path}")
                        break
                
                if connector_interface_path:
                    spec = importlib.util.spec_from_file_location("connector_interface", connector_interface_path)
                    connector_interface_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(connector_interface_module)
                    # Replace our Protocol with the actual implementation
                    ConnectorInterface = connector_interface_module.ConnectorInterface
                    logger.info("Successfully imported ConnectorInterface from file")
                else:
                    logger.error("Could not find connector_interface.py anywhere!")
                    raise ImportError("Could not find connector_interface.py")
            except Exception as e4:
                logger.error(f"All attempts to import ConnectorInterface failed: {str(e4)}")
                raise

# Import logger
from core.utils.logger import logger

# Define connector dependencies
# Key: connector name, Value: list of dependencies
# Updated: 2025-04-07T15:52:00-04:00
CONNECTOR_DEPENDENCIES = {
    # Note: Dependencies are now handled via class inheritance
    # We don't need to explicitly list websocket as a dependency for comfyui
    # since the WebSocketConnector class is imported by ComfyUIConnector
}

async def load_connectors() -> Dict[str, ConnectorInterface]:
    """Load connectors based on the CONNECTORS environment variable
    
    Returns:
        Dict[str, ConnectorInterface]: Dictionary of connector instances by job type
    """
    # Print diagnostic information to help debug package structure issues
    # This will show us what Python sees as the package structure
    print_diagnostic_info()
    
    # Get connector list from environment variable (support both namespaced and non-namespaced)
    connector_env = os.environ.get("WORKER_CONNECTORS", os.environ.get("CONNECTORS", "simulation"))
    logger.info(f"[connector_loader.py load_connectors()] WORKER_CONNECTORS environment variable: '{connector_env}'")
    
    connector_list = connector_env.split(",")
    connector_list = [c.strip() for c in connector_list if c.strip()]
    
    # We no longer need complex dependency handling since dependencies are handled via class inheritance
    # and connector_name attribute
    # Updated: 2025-04-07T15:53:00-04:00
    logger.info(f"[connector_loader.py load_connectors()] Loading connectors: {connector_list}")
    
    # Dictionary to store connector instances by job type
    connectors = {}
    
    # Dictionary to store loaded modules for dependency resolution
    loaded_modules = {}
    
    # Load each connector
    for connector_name in connector_list:
        try:
            logger.info(f"[connector_loader.py load_connectors()] Loading connector: {connector_name}")
            
            # Construct the module name
            # Define module_name here to avoid lint errors
            module_name = f"{connector_name}_connector"
            
            # Log the module name we're trying to import
            logger.info(f"[connector_loader.py load_connectors()] Trying to import module: {module_name}")
            
            # Try multiple import approaches to ensure it works in any environment
            # This is critical for Docker and other deployment environments
            module = None
            import_errors = []
            
            # First, let's search for the actual file to understand what's available
            logger.info("[connector_loader.py load_connectors()] Searching for connector file locations:")
            possible_connector_files = [
                os.path.join(os.getcwd(), "connectors", f"{module_name}.py"),
                os.path.join(os.getcwd(), "worker", "connectors", f"{module_name}.py"),
                os.path.join(os.path.dirname(__file__), "connectors", f"{module_name}.py"),
                f"/app/emp-redis-worker/worker/connectors/{module_name}.py"
            ]
            
            for path in possible_connector_files:
                if os.path.exists(path):
                    logger.info(f"[connector_loader.py load_connectors()] Found connector file at: {path}")
                else:
                    logger.info(f"[connector_loader.py load_connectors()] No connector file at: {path}")
            
            # Approach 1: Try relative import (best practice for packages)
            try:
                logger.info(f"[connector_loader.py load_connectors()] Attempting relative import: .connectors.{module_name}")
                module = importlib.import_module(f".connectors.{module_name}", package="worker")
                logger.info(f"[connector_loader.py load_connectors()] Successfully imported via relative import: .connectors.{module_name}")
            except ImportError as e1:
                error_details = str(e1)
                import_errors.append(f"Relative import error: {error_details}")
                logger.info(f"[connector_loader.py load_connectors()] Relative import failed: {error_details}")
                
                # Approach 2: Try direct import (for when files are in Python path)
                try:
                    logger.info(f"[connector_loader.py load_connectors()] Attempting direct import: connectors.{module_name}")
                    module = importlib.import_module(f"connectors.{module_name}")
                    logger.info(f"[connector_loader.py load_connectors()] Successfully imported via direct import: connectors.{module_name}")
                except ImportError as e2:
                    error_details = str(e2)
                    import_errors.append(f"Direct import error: {error_details}")
                    logger.info(f"[connector_loader.py load_connectors()] Direct import failed: {error_details}")
                    
                    # Approach 3: Try absolute import with worker prefix
                    try:
                        logger.info(f"[connector_loader.py load_connectors()] Attempting absolute import: worker.connectors.{module_name}")
                        module = importlib.import_module(f"worker.connectors.{module_name}")
                        logger.info(f"[connector_loader.py load_connectors()] Successfully imported via absolute import: worker.connectors.{module_name}")
                    except ImportError as e3:
                        error_details = str(e3)
                        import_errors.append(f"Absolute import error: {error_details}")
                        logger.info(f"[connector_loader.py load_connectors()] Absolute import failed: {error_details}")
                        
                        # Approach 4: Try emp-redis-worker specific import path
                        try:
                            logger.info(f"[connector_loader.py load_connectors()] Attempting emp-redis-worker import")
                            module = importlib.import_module(f"emp-redis-worker.worker.connectors.{module_name}")
                            logger.info(f"[connector_loader.py load_connectors()] Successfully imported via emp-redis-worker import")
                        except ImportError as e4:
                            error_details = str(e4)
                            import_errors.append(f"emp-redis-worker import error: {error_details}")
                            logger.info(f"[connector_loader.py load_connectors()] emp-redis-worker import failed: {error_details}")
                        
                            # Approach 5: Last resort - try importing the file directly
                            try:
                                # Find the connector file
                                connector_file = None
                                for path in possible_connector_files:
                                    if os.path.exists(path):
                                        connector_file = path
                                        break
                                
                                if connector_file:
                                    logger.info(f"[connector_loader.py load_connectors()] Attempting direct file import from: {connector_file}")
                                    # Import the module from file path
                                    spec = importlib.util.spec_from_file_location(module_name, connector_file)
                                    module = importlib.util.module_from_spec(spec)
                                    spec.loader.exec_module(module)
                                    logger.info(f"[connector_loader.py load_connectors()] Successfully imported directly from file: {connector_file}")
                                else:
                                    error_msg = "Could not find connector file in any expected location"
                                    logger.error(f"[connector_loader.py load_connectors()] {error_msg}")
                                    raise ImportError(error_msg)
                            except Exception as e5:
                                error_details = str(e5)
                                import_errors.append(f"File import error: {error_details}")
                                logger.info(f"[connector_loader.py load_connectors()] File import failed: {error_details}")
                                # If all approaches fail, raise a comprehensive error
                                error_msg = f"Could not import {module_name} using any method. Errors: {import_errors}"
                                logger.error(f"[connector_loader.py load_connectors()] {error_msg}")
                                raise ImportError(error_msg)
            
            if module is None:
                error_msg = f"Failed to import {module_name} using any method"
                logger.error(f"[connector_loader.py load_connectors()] {error_msg}")
                raise ImportError(error_msg)
            logger.info(f"[connector_loader.py load_connectors()] Successfully imported module: {module.__name__}")
            
            # Store the loaded module for dependency resolution
            loaded_modules[connector_name] = module
            
            # Find the connector class in the module using the connector_name attribute
            # This is more reliable than using issubclass() which can fail with aliased imports
            # Updated: 2025-04-07T15:51:00-04:00
            logger.info(f"[connector_loader.py load_connectors()] Looking for connector class with connector_name='{connector_name}' in module: {module.__name__}")
            
            connector_class = None
            for cls_name, cls in module.__dict__.items():
                if isinstance(cls, type):
                    # Log class information for debugging
                    try:
                        logger.info(f"[connector_loader.py load_connectors()] Checking class: {cls_name}, base classes: {cls.__bases__}")
                        
                        # Check if the class has the connector_name attribute matching our connector_name
                        if hasattr(cls, 'connector_name') and cls.connector_name == connector_name:
                            logger.info(f"[connector_loader.py load_connectors()] Found matching connector class: {cls_name} with connector_name='{cls.connector_name}'")
                            connector_class = cls
                            break
                    except Exception as e:
                        logger.info(f"[connector_loader.py load_connectors()] Error checking class {cls_name}: {e}")
            
            if connector_class is None:
                logger.error(f"[connector_loader.py load_connectors() ERROR] Could not find connector class with connector_name='{connector_name}' in {module.__name__}")
                continue
            
            # Create connector instance
            connector = connector_class()
            logger.info(f"[connector_loader.py load_connectors()] Created connector instance: {connector_name}")
            
            # Initialize connector
            success = await connector.initialize() #### THIS IS WHERE CONNECTORS ARE INITIALIZED
            if not success:
                logger.error(f"[connector_loader.py load_connectors() ERROR] Failed to initialize connector: {connector_name}")
                continue
            
            # Get job type from connector
            job_type = connector.get_job_type()
            
            # Add connector to dictionary
            connectors[job_type] = connector #### THIS IS WHERE CONNECTORS ARE ADDED TO THE DICTIONARY
            logger.info(f"[connector_loader.py load_connectors()] Loaded connector: {connector_name} for job type: {job_type}")
        
        except Exception as e:
            logger.error(f"[connector_loader.py load_connectors() EXCEPTION] Error loading connector {connector_name}: {str(e)}")
    
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
