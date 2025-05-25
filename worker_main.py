#!/usr/bin/env python3
# Main worker script for the EmProps Redis Worker
# Created: 2025-04-07T14:52:00-04:00
# This is the entry point script that should be run outside the worker package

import os
import sys
import traceback
import asyncio
from dotenv import load_dotenv

# Add the current directory to the Python path EARLY
# This ensures the worker package can be imported
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Import logger early for debugging
from core.utils.logger import setup_logging, logger

def log_environment_info():
    """Print environment information for debugging"""
    logger.info(f"[worker_main.py log_environment_info] Current working directory: {os.getcwd()}")
    logger.info(f"[worker_main.py log_environment_info] Looking for .env file at: {os.path.join(os.getcwd(), '.env')}")
    logger.info(f"[worker_main.py log_environment_info] Python path: {sys.path}")
    
    # Log connector-specific environment variables
    connectors = os.environ.get("WORKER_CONNECTORS", os.environ.get("CONNECTORS", "")).split(",")
    connectors = [c.strip() for c in connectors if c.strip()]
    
    for connector in connectors:
        logger.info(f"[worker_main.py log_environment_info] Environment variables for {connector} connector:")
        prefix = f"{connector.upper()}_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                logger.info(f"[worker_main.py log_environment_info] {key}: {value}")

async def main():
    """Main entry point for the worker"""
    try:
        # Load environment variables from .env file
        load_dotenv()   
        
        setup_logging()
        
        
        # Import BaseWorker from the worker package
        # This works because worker_main.py is outside the worker directory
        worker_base = None
        
        try:
            # First attempt: import from worker package
            from worker import BaseWorker
            worker_base = BaseWorker
        except ImportError as e:
            logger.error(f"[worker_main.py main] Failed to import BaseWorker from worker package: {str(e)}")
            
            # Second attempt: Try emp-redis-worker specific import for Docker environment
            try:
                # Using importlib to avoid lint errors about missing modules
                import importlib
                emp_worker_module = importlib.import_module("emp_redis_worker.worker")
                worker_base = getattr(emp_worker_module, "BaseWorker")
            except (ImportError, AttributeError) as e2:
                log_environment_info()
                error_msg = f"Failed to import BaseWorker: {str(e2)}"
                logger.error(f"[worker_main.py main] {error_msg}")
                raise ImportError(error_msg)
        
        # [2025-05-25T18:20:00-04:00] Added null check to prevent "None not callable" error
        if worker_base is None or not callable(worker_base):
            log_environment_info()
            error_msg = f"worker_base is not callable: {type(worker_base)}"
            logger.error(f"[worker_main.py main] {error_msg}")
            raise TypeError(error_msg)
            
        worker = worker_base()
        await worker.async_init()
        
        # Start the worker
        worker_task = asyncio.create_task(worker.start())
        
        # Wait for worker to finish
        await worker_task
        
    except KeyboardInterrupt:
        logger.info("[worker_main.py main] Worker stopped by user")
    except Exception as e:
        log_environment_info()
        logger.error(f"[worker_main.py main] Error starting worker: {str(e)}")
        logger.error(traceback.format_exc())
    finally:
        logger.info("[worker_main.py main] Worker shutdown")

if __name__ == "__main__":
    asyncio.run(main())
