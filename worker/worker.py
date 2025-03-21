#!/usr/bin/env python3
# Main worker script for the EmProps Redis Worker
import os
import sys
import logging
import traceback
from dotenv import load_dotenv

# Add the parent directory to the Python path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

# Add the current directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Import worker components
from base_worker import BaseWorker
from core.utils.logger import setup_logging, logger

def print_environment_info():
    """Print environment information for debugging"""
    print(f"Current working directory: {os.getcwd()}")
    print(f"Looking for .env file at: {os.path.join(os.getcwd(), '.env')}")
    
    # Print key environment variables for debugging
    print(f"REDIS_API_HOST: {os.environ.get('REDIS_API_HOST', 'not set')}")
    print(f"REDIS_API_PORT: {os.environ.get('REDIS_API_PORT', 'not set')}")
    print(f"USE_SSL: {os.environ.get('USE_SSL', 'not set')}")
    print(f"WORKER_ID: {os.environ.get('WORKER_ID', 'not set')}")
    print(f"CONNECTORS: {os.environ.get('CONNECTORS', 'not set')}")
    
    # Log connector-specific environment variables
    connectors = os.environ.get("CONNECTORS", "").split(",")
    connectors = [c.strip() for c in connectors if c.strip()]
    
    for connector in connectors:
        print(f"\nEnvironment variables for {connector} connector:")
        prefix = f"{connector.upper()}_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                print(f"  {key}: {value}")

def main():
    """Main entry point for the worker"""
    try:
        # Load environment variables from .env file
        load_dotenv()
        
        # Print environment information
        print_environment_info()
        
        # Setup logging
        log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
        setup_logging()
        
        logger.info("Starting EmProps Redis Worker")
        
        # Create and start worker
        worker = BaseWorker()
        worker.start()
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Error starting worker: {str(e)}")
        logger.error(traceback.format_exc())
    finally:
        logger.info("Worker shutdown")

if __name__ == "__main__":
    main()
