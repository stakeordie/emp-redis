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
    
    # Copy message_models.py from parent core/models to worker core/models
    src_message_models = os.path.join(parent_dir, "core", "models", "message_models.py")
    dst_message_models = os.path.join(models_dir, "message_models.py")
    if os.path.exists(src_message_models):
        print(f"Copying {src_message_models} to {dst_message_models}")
        shutil.copy2(src_message_models, dst_message_models)
    else:
        print(f"Error: message_models.py not found at {src_message_models}")
        return False
    
    # Copy base_messages.py from parent core/core_types to worker core/models
    src_base_messages = os.path.join(parent_dir, "core", "core_types", "base_messages.py")
    dst_base_messages = os.path.join(models_dir, "base_messages.py")
    if os.path.exists(src_base_messages):
        print(f"Copying {src_base_messages} to {dst_base_messages}")
        shutil.copy2(src_base_messages, dst_base_messages)
    else:
        print(f"Error: base_messages.py not found at {src_base_messages}")
        return False
    
    # Copy logger.py from parent core/utils to worker core/utils
    src_logger = os.path.join(parent_dir, "core", "utils", "logger.py")
    dst_logger = os.path.join(utils_dir, "logger.py")
    if os.path.exists(src_logger):
        print(f"Copying {src_logger} to {dst_logger}")
        shutil.copy2(src_logger, dst_logger)
    else:
        print(f"Error: logger.py not found at {src_logger}")
        return False
    
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
    content = content.replace("from .core_types.base_messages", "from .base_messages")
    content = content.replace("from .interfaces.message_models_interface", "# from .interfaces.message_models_interface")
    content = content.replace("from .utils.logger", "from ..utils.logger")
    
    with open(file_path, "w") as f:
        f.write(content)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
