#!/usr/bin/env python3
# Simulation Worker for the EmProps Redis system
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
from core.utils.logger import setup_logger, logger

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
        # Load environment variables from .env file
        load_dotenv()
        
        # Setup logging
        log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
        setup_logger(level=getattr(logging, log_level))
        
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
