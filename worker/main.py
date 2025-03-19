#!/usr/bin/env python3
# Simulation Worker for the EmProps Redis system
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
from core.utils.logger import setup_logging, logger

def setup_simulation_environment():
    """Setup environment variables for simulation mode"""
    # Force simulation connector only
    os.environ["CONNECTORS"] = "simulation"
    
    # Set default simulation settings if not already set
    if "SIMULATION_JOB_TYPE" not in os.environ:
        os.environ["SIMULATION_JOB_TYPE"] = "simulation"
    
    if "SIMULATION_PROCESSING_TIME" not in os.environ:
        os.environ["SIMULATION_PROCESSING_TIME"] = "10"
    
    if "SIMULATION_STEPS" not in os.environ:
        os.environ["SIMULATION_STEPS"] = "5"
    
    # Set worker ID if not already set
    if "WORKER_ID" not in os.environ:
        os.environ["WORKER_ID"] = "simulation-worker"
    
    logger.info("Simulation environment setup complete")
    logger.info(f"Simulation job type: {os.environ.get('SIMULATION_JOB_TYPE')}")
    logger.info(f"Simulation processing time: {os.environ.get('SIMULATION_PROCESSING_TIME')} seconds")
    logger.info(f"Simulation steps: {os.environ.get('SIMULATION_STEPS')}")

if __name__ == "__main__":
    try:
        # Print current working directory
        print(f"Current working directory: {os.getcwd()}")
        print(f"Looking for .env file at: {os.path.join(os.getcwd(), '.env')}")
        
        # Load environment variables from .env file using absolute path
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
        print(f"Loading .env from absolute path: {env_path}")
        load_dotenv(dotenv_path=env_path)
        
        # Print environment variables for debugging
        print(f"REDIS_API_HOST: {os.environ.get('REDIS_API_HOST', 'not set')}")
        print(f"REDIS_API_PORT: {os.environ.get('REDIS_API_PORT', 'not set')}")
        print(f"USE_SSL: {os.environ.get('USE_SSL', 'not set')}")
        
        # Setup logging
        log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
        setup_logging()
        
        # Setup simulation environment
        setup_simulation_environment()
        
        logger.info("Starting EmProps Redis Simulation Worker")
        
        # Create and start worker
        worker = BaseWorker()
        worker.start()
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Error: {str(e)}")
    finally:
        logger.info("Worker shutdown")
