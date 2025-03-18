import logging
import os
import sys
import time
from logging import Logger

# Create a custom Logger class with additional methods
class EnhancedLogger(Logger):
    def debug_highlight(self, msg, *args, **kwargs):
        """Enhanced debug method that makes messages stand out"""
        self.debug(f"!!!!! DEBUG: {msg} !!!!!", *args, **kwargs)

# Register our custom logger class
logging.setLoggerClass(EnhancedLogger)

def setup_logging():
    """Set up basic logging configuration"""
    # Default level from environment or DEBUG for development
    log_level_name = os.environ.get("LOG_LEVEL", "DEBUG")
    log_level = getattr(logging, log_level_name.upper(), logging.DEBUG)
    
    # Create a custom logger for the application
    app_logger = logging.getLogger("emp-redis")
    app_logger.setLevel(log_level)
    
    # Clear any existing handlers to avoid duplicate logs
    if app_logger.handlers:
        for handler in app_logger.handlers:
            app_logger.removeHandler(handler)
    
    # Create console handler with detailed formatting
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    
    # More visible format for debugging with clear separation
    log_format = "\n==== %(asctime)s - %(levelname)s ====\n%(name)s:%(lineno)d - %(message)s\n"
    formatter = logging.Formatter(log_format)
    console_handler.setFormatter(formatter)
    
    # Add handler directly to our app logger
    app_logger.addHandler(console_handler)
    
    # Print startup message
    app_logger.info(f"Logger initialized at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    return app_logger

# Initialize logging
logger = setup_logging()