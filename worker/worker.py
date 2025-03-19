#!/usr/bin/env python3
# Main worker script for the EmProps Redis Worker
import os
import sys
import logging
from dotenv import load_dotenv

# Add the parent directory to the Python path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

# Add the current directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Import worker components
from base_worker import BaseWorker
from core.utils.logger import setup_logging

def main():
    """Main entry point for the worker"""
    # Load environment variables from .env file
    load_dotenv()
    
    # Setup logging
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    setup_logging()
    
    # Create and start worker
    worker = BaseWorker()
    worker.start()

if __name__ == "__main__":
    main()
