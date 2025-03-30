#!/usr/bin/env python3
# Main worker script for the EmProps Redis Worker
import os
import sys
import traceback
from dotenv import load_dotenv

# Add the parent and current directory to the Python path EARLY
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Import logger early for debugging
from core.utils.logger import setup_logging, logger

# BaseWorker will be imported inside the main function to avoid circular imports

def log_environment_info():
    """Print environment information for debugging"""
    logger.info(f"[worker.py log_environment_info] Current working directory: {os.getcwd()}")
    logger.info(f"[worker.py log_environment_info] Looking for .env file at: {os.path.join(os.getcwd(), '.env')}")
    
    # Print key environment variables for debugging
    logger.info(f"[worker.py log_environment_info] WORKER_REDIS_API_HOST: {os.environ.get('WORKER_REDIS_API_HOST', 'not set')}")
    logger.info(f"[worker.py log_environment_info] WORKER_REDIS_API_PORT: {os.environ.get('WORKER_REDIS_API_PORT', 'not set')}")
    logger.info(f"[worker.py log_environment_info] WORKER_USE_SSL: {os.environ.get('WORKER_USE_SSL', 'not set')}")
    logger.info(f"[worker.py log_environment_info] WORKER_ID: {os.environ.get('WORKER_ID', 'not set')}")
    logger.info(f"[worker.py log_environment_info] WORKER_CONNECTORS: {os.environ.get('WORKER_CONNECTORS', 'not set')}")
    logger.info(f"[worker.py log_environment_info] WORKER_WEBSOCKET_AUTH_TOKEN: {os.environ.get('WORKER_WEBSOCKET_AUTH_TOKEN', 'not set')}")
    
    
    # Log connector-specific environment variables
    connectors = os.environ.get("CONNECTORS", "").split(",")
    connectors = [c.strip() for c in connectors if c.strip()]
    
    for connector in connectors:
        logger.info(f"[worker.py log_environment_info] Environment variables for {connector} connector:")
        prefix = f"{connector.upper()}_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                logger.info(f"[worker.py log_environment_info] {key}: {value}")

async def main():
    """Main entry point for the worker"""
    try:
        # Print environment information
        log_environment_info()

        # Load environment variables from .env file
        if not os.environ.get("WORKER_REDIS_API_HOST"):
            load_dotenv()   
        
        # Print environment information
        log_environment_info()
        
        # Setup logging
        log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
        setup_logging()
        
        logger.info("[worker.py main] Starting EmProps Redis Worker")
        
        # Import BaseWorker here to avoid circular imports
        from base_worker import BaseWorker
        
        # Create and start worker
        worker = BaseWorker() ## base_worker.py

        await worker.async_init()
        ### THIS IS WHERE THE WORKER STARTS ###
        worker_task = asyncio.create_task(worker.start())
        
        # Wait for worker to finish
        await worker_task
    except KeyboardInterrupt:
        logger.info("[worker.py main] Worker stopped by user")
    except Exception as e:
        logger.error(f"[worker.py main] Error starting worker: {str(e)}")
        logger.error(traceback.format_exc())
    finally:
        logger.info("[worker.py main] Worker shutdown")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
