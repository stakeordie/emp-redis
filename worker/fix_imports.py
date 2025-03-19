#!/usr/bin/env python3
# Helper script to fix imports in the Docker container
import os
import sys
import shutil

def main():
    """Create symlinks or copy necessary files for imports to work in Docker"""
    print("Fixing imports for Docker container...")
    
    # Get current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"Current directory: {current_dir}")
    
    # Get parent directory
    parent_dir = os.path.dirname(current_dir)
    print(f"Parent directory: {parent_dir}")
    
    # Check if core directory exists in parent
    core_dir = os.path.join(parent_dir, "core")
    if not os.path.exists(core_dir):
        print(f"Error: Core directory not found at {core_dir}")
        return False
    
    # Create core directory in worker if it doesn't exist
    worker_core_dir = os.path.join(current_dir, "core")
    if not os.path.exists(worker_core_dir):
        print(f"Creating core directory at {worker_core_dir}")
        os.makedirs(worker_core_dir)
    
    # Create __init__.py file in core directory
    init_file = os.path.join(worker_core_dir, "__init__.py")
    if not os.path.exists(init_file):
        print(f"Creating {init_file}")
        with open(init_file, "w") as f:
            f.write("# Auto-generated __init__.py file\n")
    
    # Create models directory in core if it doesn't exist
    models_dir = os.path.join(worker_core_dir, "models")
    if not os.path.exists(models_dir):
        print(f"Creating models directory at {models_dir}")
        os.makedirs(models_dir)
    
    # Create __init__.py file in models directory
    models_init_file = os.path.join(models_dir, "__init__.py")
    if not os.path.exists(models_init_file):
        print(f"Creating {models_init_file}")
        with open(models_init_file, "w") as f:
            f.write("# Auto-generated __init__.py file\n")
    
    # Create utils directory in core if it doesn't exist
    utils_dir = os.path.join(worker_core_dir, "utils")
    if not os.path.exists(utils_dir):
        print(f"Creating utils directory at {utils_dir}")
        os.makedirs(utils_dir)
    
    # Create __init__.py file in utils directory
    utils_init_file = os.path.join(utils_dir, "__init__.py")
    if not os.path.exists(utils_init_file):
        print(f"Creating {utils_init_file}")
        with open(utils_init_file, "w") as f:
            f.write("# Auto-generated __init__.py file\n")
            
    # Copy connector_interface.py if it doesn't exist
    dst_connector_interface = os.path.join(current_dir, "connector_interface.py")
    if not os.path.exists(dst_connector_interface):
        src_connector_interface = os.path.join(parent_dir, "worker", "connector_interface.py")
        if os.path.exists(src_connector_interface):
            print(f"Copying {src_connector_interface} to {dst_connector_interface}")
            shutil.copy2(src_connector_interface, dst_connector_interface)
        else:
            print("Creating a simple connector_interface.py")
            with open(dst_connector_interface, "w") as f:
                f.write('''
#!/usr/bin/env python3
# Connector interface for the EmProps Redis Worker
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Union

class ConnectorInterface(ABC):
    """Interface for service connectors that handle specific job types"""
    
    @abstractmethod
    def initialize(self) -> bool:
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
''')
                
    # Create a symbolic link to connector_loader.py if it doesn't exist
    dst_connector_loader = os.path.join(current_dir, "connector_loader.py")
    if not os.path.exists(dst_connector_loader):
        src_connector_loader = os.path.join(parent_dir, "worker", "connector_loader.py")
        if os.path.exists(src_connector_loader):
            print(f"Copying {src_connector_loader} to {dst_connector_loader}")
            shutil.copy2(src_connector_loader, dst_connector_loader)
    
    # Copy message_models.py from parent core/models to worker core/models
    # Try different possible locations
    possible_message_models_paths = [
        os.path.join(parent_dir, "core", "models", "message_models.py"),
        os.path.join(parent_dir, "core", "message_models.py")
    ]
    
    src_message_models = None
    for path in possible_message_models_paths:
        if os.path.exists(path):
            src_message_models = path
            break
    
    dst_message_models = os.path.join(models_dir, "message_models.py")
    
    if src_message_models:
        print(f"Copying {src_message_models} to {dst_message_models}")
        shutil.copy2(src_message_models, dst_message_models)
    else:
        print("Error: message_models.py not found in any expected location")
        # Create a simple message_models.py
        print("Creating a simple message_models.py")
        with open(dst_message_models, "w") as f:
            f.write('''
# Simple message models implementation
import asyncio
from enum import Enum
from typing import Dict, List, Any, Optional

class MessageType(Enum):
    """Message type enum"""
    HEARTBEAT = "heartbeat"
    STATUS = "status"
    JOB_REQUEST = "job_request"
    JOB_RESPONSE = "job_response"
    JOB_STATUS = "job_status"

class MessageModelsInterface:
    """Interface for message models"""
    @staticmethod
    def create_heartbeat_message(worker_id, status, current_job_id=None):
        """Create heartbeat message"""
        pass
        
    @staticmethod
    def create_worker_status_message(worker_id, status, capabilities):
        """Create worker status message"""
        pass

class MessageModels(MessageModelsInterface):
    """Simple implementation of MessageModels"""
    @staticmethod
    def create_heartbeat_message(worker_id: str, status: str, current_job_id: Optional[str] = None) -> Dict[str, Any]:
        return {
            "type": MessageType.HEARTBEAT.value,
            "worker_id": worker_id,
            "status": status,
            "current_job_id": current_job_id,
            "timestamp": asyncio.get_event_loop().time()
        }
    
    @staticmethod
    def create_worker_status_message(worker_id: str, status: str, capabilities: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": MessageType.STATUS.value,
            "worker_id": worker_id,
            "status": status,
            "capabilities": capabilities,
            "timestamp": asyncio.get_event_loop().time()
        }
''')
    
    # Copy base_messages.py from parent core/core_types to worker core/models
    # Try different possible locations
    possible_base_messages_paths = [
        os.path.join(parent_dir, "core", "core_types", "base_messages.py"),
        os.path.join(parent_dir, "core", "base_messages.py")
    ]
    
    src_base_messages = None
    for path in possible_base_messages_paths:
        if os.path.exists(path):
            src_base_messages = path
            break
    
    dst_base_messages = os.path.join(models_dir, "base_messages.py")
    
    if src_base_messages:
        print(f"Copying {src_base_messages} to {dst_base_messages}")
        shutil.copy2(src_base_messages, dst_base_messages)
    else:
        print("Error: base_messages.py not found in any expected location")
        # Create a simple base_messages.py
        print("Creating a simple base_messages.py")
        with open(dst_base_messages, "w") as f:
            f.write('''
# Simple base messages implementation
from typing import Dict, Any, Optional

class BaseMessage:
    """Base class for all messages"""
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary"""
        return {}
''')
    
    # Copy logger.py from parent core/utils to worker core/utils
    # Try different possible locations
    possible_logger_paths = [
        os.path.join(parent_dir, "core", "utils", "logger.py"),
        os.path.join(parent_dir, "core", "logger.py")
    ]
    
    src_logger = None
    for path in possible_logger_paths:
        if os.path.exists(path):
            src_logger = path
            break
    
    dst_logger = os.path.join(utils_dir, "logger.py")
    
    if src_logger:
        print(f"Copying {src_logger} to {dst_logger}")
        shutil.copy2(src_logger, dst_logger)
    else:
        print("Error: logger.py not found in any expected location")
        # Create a simple logger.py
        print("Creating a simple logger.py")
        with open(dst_logger, "w") as f:
            f.write('''
# Simple logger implementation
import logging
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Create logger
logger = logging.getLogger('worker')

# Set log level from environment variable if available
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logger.setLevel(getattr(logging, log_level, logging.INFO))

def setup_logger(name=None, level=None):
    """Setup logger with specified name and level
    
    Args:
        name (str, optional): Logger name. Defaults to None.
        level (str, optional): Log level. Defaults to None.
        
    Returns:
        logging.Logger: Configured logger
    """
    if name is None:
        return logger
        
    _logger = logging.getLogger(name)
    
    if level is not None:
        _logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    return _logger
''')
    
    # Update imports in copied files to make them work locally
    update_imports(dst_message_models)
    update_imports(dst_base_messages)
    update_imports(dst_logger)
    
    print("Import fixes completed successfully!")
    return True

def update_imports(file_path):
    """Update imports in copied files to make them work locally"""
    print(f"Updating imports in {file_path}")
    
    with open(file_path, "r") as f:
        content = f.read()
    
    # Replace imports to make them work locally
    replacements = [
        # Base messages imports
        ("from .core_types.base_messages", "from .base_messages"),
        ("from core.core_types.base_messages", "from .base_messages"),
        
        # Interface imports (comment out if not available)
        ("from .interfaces.message_models_interface", "# from .interfaces.message_models_interface"),
        ("from core.interfaces.message_models_interface", "# from core.interfaces.message_models_interface"),
        
        # Logger imports
        ("from .utils.logger", "from ..utils.logger"),
        ("from core.utils.logger", "from ..utils.logger"),
        
        # Other potential imports
        ("from core.models.", "from ."),
        ("from core.utils.", "from ..utils."),
    ]
    
    for old, new in replacements:
        content = content.replace(old, new)
    
    # Special handling for MessageModelsInterface
    if "MessageModelsInterface" in content and "class MessageModelsInterface" not in content:
        # Add MessageModelsInterface class definition
        interface_def = '''
# Added MessageModelsInterface definition
class MessageModelsInterface:
    """Interface for message models"""
    @staticmethod
    def create_heartbeat_message(worker_id, status, current_job_id=None):
        """Create heartbeat message"""
        pass
        
    @staticmethod
    def create_worker_status_message(worker_id, status, capabilities):
        """Create worker status message"""
        pass

'''
        # Insert the interface definition before the first class definition
        if "class " in content:
            insert_pos = content.find("class ")
            content = content[:insert_pos] + interface_def + content[insert_pos:]
        else:
            content = interface_def + content
    
    with open(file_path, "w") as f:
        f.write(content)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
