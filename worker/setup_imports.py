#!/usr/bin/env python3
# Helper script to setup imports in any environment
import os
import sys

def setup_imports():
    """Setup Python path to make imports work in any environment"""
    print("Setting up imports...")
    
    # Get current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"Current directory: {current_dir}")
    
    # Get parent directory
    parent_dir = os.path.dirname(current_dir)
    print(f"Parent directory: {parent_dir}")
    
    # Add parent directory to Python path if not already there
    if parent_dir not in sys.path:
        print(f"Adding to Python path: {parent_dir}")
        sys.path.insert(0, parent_dir)
    
    # Add current directory to Python path if not already there
    if current_dir not in sys.path:
        print(f"Adding to Python path: {current_dir}")
        sys.path.insert(0, current_dir)
    
    # Create core directory structure if needed
    core_dir = os.path.join(current_dir, "core")
    models_dir = os.path.join(core_dir, "models")
    utils_dir = os.path.join(core_dir, "utils")
    
    # Create directories if they don't exist
    os.makedirs(models_dir, exist_ok=True)
    os.makedirs(utils_dir, exist_ok=True)
    
    # Create __init__.py files
    create_init_file(core_dir)
    create_init_file(models_dir)
    create_init_file(utils_dir)
    
    # Print the Python path for debugging
    print(f"Python path: {sys.path}")
    
    return True

def create_init_file(directory):
    """Create __init__.py file in directory if it doesn't exist"""
    init_file = os.path.join(directory, "__init__.py")
    if not os.path.exists(init_file):
        print(f"Creating {init_file}")
        with open(init_file, "w") as f:
            f.write("# Auto-generated __init__.py file\n")

if __name__ == "__main__":
    setup_imports()
