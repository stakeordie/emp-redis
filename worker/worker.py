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
    logger.debug(f"[worker.py log_environment_info] Current working directory: {os.getcwd()}")
    logger.debug(f"[worker.py log_environment_info] Looking for .env file at: {os.path.join(os.getcwd(), '.env')}")
    
    # Log connector-specific environment variables
    connectors = os.environ.get("CONNECTORS", "").split(",")
    connectors = [c.strip() for c in connectors if c.strip()]
    
    for connector in connectors:
        logger.debug(f"[worker.py log_environment_info] Environment variables for {connector} connector:")
        prefix = f"{connector.upper()}_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                logger.debug(f"[worker.py log_environment_info] {key}: {value}")

async def main():
    """Main entry point for the worker"""
    try:

        # Load environment variables from .env file
        load_dotenv()   
        
        # Print environment information
        # log_environment_info()
        
        # Setup logging
        log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
        setup_logging()
        
        logger.debug("[worker.py main] Starting EmProps Redis Worker")
        
        # Import BaseWorker here to avoid circular imports
        # Use package imports to leverage __init__.py
        logger.debug("[worker.py main] Importing BaseWorker")
        
        # Define BaseWorker variable
        BaseWorker = None
        import_success = False
        
        # Approach 1: Try importing from worker package (best practice)
        try:
            from worker import BaseWorker as WorkerBaseWorker
            BaseWorker = WorkerBaseWorker
            import_success = True
        except ImportError as e:
            log_environment_info()
            logger.error(f"[worker.py main] Failed to import BaseWorker from worker package: {str(e)}")
        
        # Approach 2: Try direct import
        if not import_success:
            
            try:
                from base_worker import BaseWorker as DirectBaseWorker
                BaseWorker = DirectBaseWorker
                import_success = True
            except ImportError as e2:   
                log_environment_info()
                logger.error(f"[worker.py main] Failed direct import of BaseWorker: {str(e2)}")
        
        # Approach 3: Try emp-redis-worker specific import
        if not import_success:
            
            try:
                from emp_redis_worker.worker import BaseWorker as EmpBaseWorker
                BaseWorker = EmpBaseWorker
                import_success = True
            except ImportError as e3:
                log_environment_info()
                logger.error(f"[worker.py main] Failed emp-redis-worker import of BaseWorker: {str(e3)}")
        
        # Check if any import approach succeeded
        if not import_success or BaseWorker is None:
            log_environment_info()
            error_msg = "Failed to import BaseWorker using any approach"
            logger.error(f"[worker.py main] {error_msg}")
            raise ImportError(error_msg)
        
        # [2025-05-25T18:00:00-04:00] Added explicit type check to prevent "None not callable" error
        if not callable(BaseWorker):
            log_environment_info()
            error_msg = f"BaseWorker is not callable: {type(BaseWorker)}"
            logger.error(f"[worker.py main] {error_msg}")
            raise TypeError(error_msg)
            
        # Create and start worker
        worker = BaseWorker() ## base_worker.py

        await worker.async_init()
        ### THIS IS WHERE THE WORKER STARTS ###
        worker_task = asyncio.create_task(worker.start())
        
        # Wait for worker to finish
        await worker_task
    except KeyboardInterrupt:
        logger.debug("[worker.py main] Worker stopped by user")
    except Exception as e:
        log_environment_info()
        logger.error(f"[worker.py main] Error starting worker: {str(e)}")
        logger.error(traceback.format_exc())
    finally:
        logger.debug("[worker.py main] Worker shutdown")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
