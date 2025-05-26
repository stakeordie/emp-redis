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
    # [2025-05-25T21:40:00-04:00] Enhanced logging for better diagnostics
    # [2025-05-25T21:40:00-04:00] Using debug level for diagnostic messages so they can be easily removed later
    logger.debug(f"[worker_main.py log_environment_info] Current working directory: {os.getcwd()}")
    logger.debug(f"[worker_main.py log_environment_info] Looking for .env file at: {os.path.join(os.getcwd(), '.env')}")
    logger.debug(f"[worker_main.py log_environment_info] Python path: {sys.path}")
    
    # Log all environment variables for debugging
    logger.debug(f"[worker_main.py log_environment_info] Environment variables:")
    for key, value in sorted(os.environ.items()):
        logger.debug(f"[worker_main.py log_environment_info] {key}: {value}")
    
    # Check if key directories and files exist
    logger.debug(f"[worker_main.py log_environment_info] Checking for key files and directories:")
    paths_to_check = [
        "worker",
        "worker/__init__.py",
        "worker/base_worker.py",
        "core",
        "core/__init__.py",
        "core/message_models.py",
        "core/core_types",
        "core/core_types/__init__.py",
        "core/core_types/message_models.py"
    ]
    
    for path in paths_to_check:
        full_path = os.path.join(os.getcwd(), path)
        exists = os.path.exists(full_path)
        logger.debug(f"[worker_main.py log_environment_info] {path}: {'EXISTS' if exists else 'MISSING'}")
        
        # If it's a Python file that exists, log its size and modification time
        if exists and path.endswith('.py'):
            size = os.path.getsize(full_path)
            mtime = os.path.getmtime(full_path)
            logger.debug(f"[worker_main.py log_environment_info] {path}: Size={size} bytes, Modified={mtime}")
            
            # Log the first few lines of key files
            if path in ["worker/__init__.py", "worker/base_worker.py"]:
                try:
                    with open(full_path, 'r') as f:
                        first_lines = '\n'.join(f.readlines()[:10])
                        logger.debug(f"[worker_main.py log_environment_info] First 10 lines of {path}:\n{first_lines}")
                except Exception as e:
                    logger.error(f"[worker_main.py log_environment_info] Error reading {path}: {str(e)}")
    
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
        
        # [2025-05-25T21:45:00-04:00] Enhanced import error handling with detailed diagnostics
        import_errors = []
        
        try:
            # First attempt: import from worker package
            logger.debug(f"[2025-05-25T21:45:00-04:00] Attempting to import BaseWorker from worker package")
            from worker import BaseWorker
            worker_base = BaseWorker
            logger.debug(f"[2025-05-25T21:45:00-04:00] Successfully imported BaseWorker from worker package")
        except ImportError as e:
            error_details = f"Failed to import BaseWorker from worker package: {str(e)}"
            import_errors.append(error_details)
            logger.debug(f"[2025-05-25T21:45:00-04:00] {error_details}")
            
            # Try to inspect the worker package
            try:
                import worker
                logger.debug(f"[2025-05-25T21:45:00-04:00] worker package exists, dir(worker): {dir(worker)}")
            except ImportError as e_worker:
                logger.debug(f"[2025-05-25T21:45:00-04:00] Cannot import worker package at all: {str(e_worker)}")
            
            # Second attempt: Try direct import from base_worker module
            try:
                logger.debug(f"[2025-05-25T21:45:00-04:00] Attempting to import BaseWorker directly from worker.base_worker")
                from worker.base_worker import BaseWorker
                worker_base = BaseWorker
                logger.debug(f"[2025-05-25T21:45:00-04:00] Successfully imported BaseWorker directly from worker.base_worker")
            except ImportError as e_direct:
                error_details = f"Failed to import BaseWorker directly from worker.base_worker: {str(e_direct)}"
                import_errors.append(error_details)
                logger.debug(f"[2025-05-25T21:45:00-04:00] {error_details}")
                
                # Try to load the module directly from the file
                import os.path
                import importlib.util
                base_worker_path = os.path.join(current_dir, 'worker', 'base_worker.py')
                if os.path.exists(base_worker_path):
                    logger.debug(f"[2025-05-25T21:45:00-04:00] Attempting direct file import from {base_worker_path}")
                    spec = importlib.util.spec_from_file_location("base_worker", base_worker_path)
                    base_worker_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(base_worker_module)
                    
                    if hasattr(base_worker_module, 'BaseWorker'):
                        worker_base = base_worker_module.BaseWorker
                        logger.debug(f"[2025-05-25T21:45:00-04:00] Successfully imported BaseWorker directly from file")
                
                # Third attempt: Try emp-redis-worker specific import for Docker environment
                try:
                    logger.debug(f"[2025-05-25T21:45:00-04:00] Attempting to import BaseWorker from emp_redis_worker.worker")
                    # Using importlib for more flexible imports
                    import importlib
                    emp_worker_module = importlib.import_module("emp_redis_worker.worker")
                    worker_base = getattr(emp_worker_module, "BaseWorker")
                    logger.debug(f"[2025-05-25T21:45:00-04:00] Successfully imported BaseWorker from emp_redis_worker.worker")
                except (ImportError, AttributeError) as e_emp:
                    error_details = f"Failed to import BaseWorker from emp_redis_worker.worker: {str(e_emp)}"
                    import_errors.append(error_details)
                    logger.error(f"[2025-05-25T21:45:00-04:00] {error_details}")
                    
                    # Log detailed environment information for debugging
                    log_environment_info()
                    
                    # Provide a comprehensive error message with all attempts
                    error_msg = f"Failed to import BaseWorker after multiple attempts:\n" + "\n".join(import_errors)
                    logger.error(f"[2025-05-25T21:45:00-04:00] {error_msg}")
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
