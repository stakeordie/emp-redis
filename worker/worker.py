#!/usr/bin/env python3
# Main worker script for the EmProps Redis Worker
import os
import sys
import logging
from dotenv import load_dotenv

# Add parent directory to path for imports
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
print(f"Current directory: {os.getcwd()}")
print(f"Adding to Python path: {parent_dir}")
sys.path.insert(0, parent_dir)

# Also add the current directory to the path
current_dir = os.path.dirname(os.path.abspath(__file__))
print(f"Also adding to Python path: {current_dir}")
sys.path.insert(0, current_dir)

# Print the Python path for debugging
print(f"Python path: {sys.path}")

# Import worker components
from base_worker import BaseWorker
from core.utils.logger import setup_logger

def main():
    """Main entry point for the worker"""
    # Load environment variables from .env file
    load_dotenv()
    
    # Setup logging
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    setup_logger(level=getattr(logging, log_level))
    
    # Create and start worker
    worker = BaseWorker()
    worker.start()

if __name__ == "__main__":
    main()
