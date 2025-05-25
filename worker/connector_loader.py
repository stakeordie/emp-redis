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

# Import logger first so we can use it in the import block
from core.utils.logger import logger

# [2025-05-25T17:30:00-04:00] Removed Protocol definition to avoid type conflicts
# We'll use the actual ConnectorInterface class from the import below
# This avoids having two different definitions of ConnectorInterface

# [2025-05-25T17:10:00-04:00] Simplified ConnectorInterface import to fix type errors
# Import directly from the most likely location to avoid type conflicts
# [2025-05-25T17:50:00-04:00] Define a type variable for ConnectorInterface
# This will be used throughout the code instead of directly using the imported type
ConnectorInterface_class = None

try:
    # First try worker package import (most common in production)
    from worker.connector_interface import ConnectorInterface
    # Store the class in our variable
    ConnectorInterface_class = ConnectorInterface
except ImportError as e:
    logger.error(f"[2025-05-25T17:50:00-04:00] Failed to import ConnectorInterface from worker package: {str(e)}")
    # Fall back to relative import (common in development)
    try:
        from .connector_interface import ConnectorInterface
        # Store the class in our variable
        ConnectorInterface_class = ConnectorInterface
        logger.error("[2025-05-25T17:50:00-04:00] Successfully imported ConnectorInterface via relative import")
    except ImportError as e2:
        logger.error(f"[2025-05-25T17:10:15-04:00] Failed to import ConnectorInterface via relative import: {str(e2)}")
        # Last resort - direct import
        try:
            # [2025-05-25T17:45:00-04:00] Import with a different name to avoid redefinition
            # and use a variable to store the class instead of assigning directly to the type
            from connector_interface import ConnectorInterface as DirectConnectorInterface
            # Create a variable with the same name to use throughout the code
            # This avoids assigning to a type directly
            ConnectorInterface_class = DirectConnectorInterface
            logger.error("[2025-05-25T17:40:00-04:00] Successfully imported ConnectorInterface via direct import")
        except ImportError as e3:
            logger.error(f"[2025-05-25T17:10:15-04:00] Failed to import ConnectorInterface via all standard methods: {str(e3)}")
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
                        logger.error(f"Found connector_interface.py at: {path}")
                        break
                
                if connector_interface_path:
                    spec = importlib.util.spec_from_file_location("connector_interface", connector_interface_path)
                    # [2025-05-25T17:15:00-04:00] Added null check for spec to prevent type errors
                    if spec is not None and spec.loader is not None:
                        connector_interface_module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(connector_interface_module)
                        # [2025-05-25T17:35:00-04:00] Fixed type error with getattr
                        # Import the ConnectorInterface class from the module
                        from types import ModuleType
                        module: ModuleType = connector_interface_module
                        # Use getattr to get the ConnectorInterface class
                        # We're using a type annotation to tell mypy this is the correct type
                        from typing import cast, Type
                        ConnectorInterface_class = getattr(module, 'ConnectorInterface')
                        # This is a type-safe way to handle the dynamic import
                        # without causing type errors
                        logger.error("[2025-05-25T17:15:15-04:00] Successfully imported ConnectorInterface from file")
                    else:
                        logger.error("[2025-05-25T17:15:15-04:00] Invalid module spec for connector_interface.py")
                        raise ImportError("Invalid module spec for connector_interface.py")
                else:
                    logger.error("[2025-05-25T17:15:15-04:00] Could not find connector_interface.py anywhere!")
                    raise ImportError("Could not find connector_interface.py")
            except Exception as e4:
                logger.error(f"All attempts to import ConnectorInterface failed: {str(e4)}")
                raise

# Define connector dependencies
# Key: connector name, Value: list of dependencies
# Updated: 2025-04-07T15:52:00-04:00
# [2025-05-25T17:20:00-04:00] Added type annotation to fix mypy error
CONNECTOR_DEPENDENCIES: Dict[str, List[str]] = {
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
    
    # Get connector list from environment variable (support both namespaced and non-namespaced)
    connector_env = os.environ.get("WORKER_CONNECTORS", os.environ.get("CONNECTORS", "simulation"))
    
    connector_list = connector_env.split(",")
    connector_list = [c.strip() for c in connector_list if c.strip()]
    
    # We no longer need complex dependency handling since dependencies are handled via class inheritance
    # and connector_name attribute
    # Updated: 2025-04-07T15:53:00-04:00
    
    # Dictionary to store connector instances by job type
    connectors = {}
    
    # Dictionary to store loaded modules for dependency resolution
    loaded_modules = {}
    
    # Load each connector
    for connector_name in connector_list:
        try:
            
            # Construct the module name
            # Define module_name here to avoid lint errors
            module_name = f"{connector_name}_connector"
            
            # Log the module name we're trying to import
            
            # Try multiple import approaches to ensure it works in any environment
            # This is critical for Docker and other deployment environments
            module = None
            import_errors = []
            
            # First, let's search for the actual file to understand what's available
            possible_connector_files = [
                os.path.join(os.getcwd(), "connectors", f"{module_name}.py"),
                os.path.join(os.getcwd(), "worker", "connectors", f"{module_name}.py"),
                os.path.join(os.path.dirname(__file__), "connectors", f"{module_name}.py"),
                f"/app/emp-redis-worker/worker/connectors/{module_name}.py"
            ]

            # Approach 1: Try relative import (best practice for packages)
            try:
                module = importlib.import_module(f".connectors.{module_name}", package="worker")
            except ImportError as e1:
                error_details = str(e1)
                import_errors.append(f"Relative import error: {error_details}")
                logger.error(f"[connector_loader.py load_connectors()] Relative import failed: {error_details}")
                
                # Approach 2: Try direct import (for when files are in Python path)
                try:
                    logger.error(f"[connector_loader.py load_connectors()] Attempting direct import: connectors.{module_name}")
                    module = importlib.import_module(f"connectors.{module_name}")
                    logger.error(f"[connector_loader.py load_connectors()] Successfully imported via direct import: connectors.{module_name}")
                except ImportError as e2:
                    error_details = str(e2)
                    import_errors.append(f"Direct import error: {error_details}")
                    logger.error(f"[connector_loader.py load_connectors()] Direct import failed: {error_details}")
                    
                    # Approach 3: Try absolute import with worker prefix
                    try:
                        logger.error(f"[connector_loader.py load_connectors()] Attempting absolute import: worker.connectors.{module_name}")
                        module = importlib.import_module(f"worker.connectors.{module_name}")
                        logger.error(f"[connector_loader.py load_connectors()] Successfully imported via absolute import: worker.connectors.{module_name}")
                    except ImportError as e3:
                        error_details = str(e3)
                        import_errors.append(f"Absolute import error: {error_details}")
                        logger.error(f"[connector_loader.py load_connectors()] Absolute import failed: {error_details}")
                        
                        # Approach 4: Try emp-redis-worker specific import path
                        try:
                            logger.error(f"[connector_loader.py load_connectors()] Attempting emp-redis-worker import")
                            module = importlib.import_module(f"emp-redis-worker.worker.connectors.{module_name}")
                            logger.error(f"[connector_loader.py load_connectors()] Successfully imported via emp-redis-worker import")
                        except ImportError as e4:
                            error_details = str(e4)
                            import_errors.append(f"emp-redis-worker import error: {error_details}")
                            logger.error(f"[connector_loader.py load_connectors()] emp-redis-worker import failed: {error_details}")
                        
                            # Approach 5: Last resort - try importing the file directly
                            try:
                                # Find the connector file
                                connector_file = None
                                for path in possible_connector_files:
                                    if os.path.exists(path):
                                        connector_file = path
                                        break
                                
                                if connector_file:
                                    logger.error(f"[connector_loader.py load_connectors()] Attempting direct file import from: {connector_file}")
                                    # Import the module from the spec
                                    spec = importlib.util.spec_from_file_location(module_name, connector_file)
                                    # [2025-05-25T17:25:00-04:00] Added null check for spec to prevent type errors
                                    if spec is not None and spec.loader is not None:
                                        module = importlib.util.module_from_spec(spec)
                                        spec.loader.exec_module(module)
                                        
                                        # Get the connector class from the module
                                    else:
                                        logger.error(f"[2025-05-25T17:25:15-04:00] Invalid module spec for {connector_file}")
                                        raise ImportError(f"Invalid module spec for {connector_file}")
                                else:
                                    error_msg = "Could not find connector file in any expected location"
                                    logger.error(f"[connector_loader.py load_connectors()] {error_msg}")
                                    raise ImportError(error_msg)
                            except Exception as e5:
                                error_details = str(e5)
                                import_errors.append(f"File import error: {error_details}")
                                logger.error(f"[connector_loader.py load_connectors()] File import failed: {error_details}")
                                # If all approaches fail, raise a comprehensive error
                                error_msg = f"Could not import {module_name} using any method. Errors: {import_errors}"
                                logger.error(f"[connector_loader.py load_connectors()] {error_msg}")
                                raise ImportError(error_msg)
            
            if module is None:
                error_msg = f"Failed to import {module_name} using any method"
                logger.error(f"[connector_loader.py load_connectors()] {error_msg}")
                raise ImportError(error_msg)
            logger.error(f"[connector_loader.py load_connectors()] Successfully imported module: {module.__name__}")
            
            # Store the loaded module for dependency resolution
            loaded_modules[connector_name] = module
            
            # [2025-05-25T22:00:00-04:00] Simplified connector class finding logic to be more reliable
            # Support both the new connector_id property and the old connector_name attribute
            connector_class = None
            for cls_name, cls in module.__dict__.items():
                if not isinstance(cls, type):
                    continue
                    
                # Skip if not a ConnectorInterface subclass
                try:
                    if not issubclass(cls, ConnectorInterface):
                        continue
                except TypeError:
                    # This happens for non-class objects
                    continue
                    
                # Skip abstract base classes
                if cls == ConnectorInterface or cls.__name__ == 'WebSocketConnector':
                    continue
                    
                # First try the new connector_id property approach
                try:
                    # Create a temporary instance
                    instance = cls()
                    # Check if connector_id property matches
                    if hasattr(instance, 'connector_id') and callable(getattr(instance, 'connector_id')):
                        if instance.connector_id == connector_name:
                            connector_class = cls
                            logger.info(f"[connector_loader.py load_connectors()] Found connector class {cls_name} with connector_id='{connector_name}'")
                            break
                except Exception as e:
                    # Fall back to checking connector_name attribute
                    try:
                        if hasattr(cls, 'connector_name') and cls.connector_name == connector_name:
                            connector_class = cls
                            logger.info(f"[connector_loader.py load_connectors()] Found connector class {cls_name} with connector_name='{connector_name}'")
                            break
                    except Exception as nested_e:
                        logger.error(f"[connector_loader.py load_connectors()] Error checking class {cls_name}: {e}, {nested_e}")
                        continue
            
            if connector_class is None:
                logger.error(f"[connector_loader.py load_connectors() ERROR] Could not find connector class with connector_id='{connector_name}' in {module.__name__}")
                # Log available classes for debugging
                try:
                    class_info = [f"{cls_name}: is ConnectorInterface subclass={issubclass(cls, ConnectorInterface) if isinstance(cls, type) else False}" 
                                 for cls_name, cls in module.__dict__.items() if isinstance(cls, type)]
                    logger.error(f"[connector_loader.py load_connectors() DEBUG] Available classes in {module.__name__}: {class_info}")
                except Exception as e:
                    logger.error(f"[connector_loader.py load_connectors() DEBUG] Error getting class info: {e}")
                continue
            
            # Create connector instance
            connector = connector_class()            
            # Initialize connector
            success = await connector.initialize() #### THIS IS WHERE CONNECTORS ARE INITIALIZED
            if not success:
                logger.error(f"[connector_loader.py load_connectors() ERROR] Failed to initialize connector: {connector_name}")
                continue
            
            # Get job type from connector
            job_type = connector.get_job_type()
            
            # Add connector to dictionary
            connectors[job_type] = connector #### THIS IS WHERE CONNECTORS ARE ADDED TO THE DICTIONARY
        
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
    # Get supported job types
    supported_job_types = get_supported_job_types(connectors)
    
    # Base capabilities
    capabilities = {
        "version": "1.0.0",
        "supported_job_types": supported_job_types,
        "cpu": True,
        "memory": "16GB",
    }
    
    # Add connector-specific capabilities
    for job_type, connector in connectors.items():
        connector_capabilities = connector.get_capabilities()        
        # [2025-05-25T17:25:30-04:00] Ensure connector_capabilities is a dict before iterating
        if isinstance(connector_capabilities, dict):
            for key, value in connector_capabilities.items():
                # Add connector prefix to avoid conflicts
                capabilities[f"{job_type}_{key}"] = value
        else:
            logger.error(f"[2025-05-25T17:25:30-04:00] Connector {job_type} returned non-dict capabilities: {connector_capabilities}")
            # Skip this connector's capabilities
        
    return capabilities
