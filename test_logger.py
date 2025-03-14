#!/usr/bin/env python3
# Simple script to test the logger functionality
from core.utils.logger import logger

print("\n\n==== DIRECT PRINT: TESTING LOGGER ====\n\n")

# Test standard logging methods
logger.debug("This is a DEBUG message")
logger.info("This is an INFO message")
logger.warning("This is a WARNING message")
logger.error("This is an ERROR message")

# Test our custom debug_highlight method
try:
    logger.debug_highlight("This is a HIGHLIGHTED DEBUG message")
    print("\n\n==== DIRECT PRINT: debug_highlight method exists! ====\n\n")
except AttributeError as e:
    print(f"\n\n==== DIRECT PRINT: debug_highlight method does not exist: {str(e)} ====\n\n")

print("\n\n==== DIRECT PRINT: LOGGER TEST COMPLETE ====\n\n")
