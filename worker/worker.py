#!/usr/bin/env python3
# Main worker script for the EmProps Redis Worker
import os
import sys
import logging
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
