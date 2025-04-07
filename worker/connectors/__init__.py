#!/usr/bin/env python3
# EmProps Redis Worker Connectors Package
# Created: 2025-04-07T11:04:00-04:00
# Updated: 2025-04-07T11:13:00-04:00

"""
EmProps Redis Worker Connectors package.

This package contains connector implementations for the EmProps Redis Worker.
Connectors allow the worker to communicate with various external services through
different protocols (WebSocket, REST, etc.).
"""

# Base connectors - these provide common functionality for specific service connectors
# Make them available at the package level for easy imports like:
# from worker.connectors import WebSocketConnector

# Base connector classes
try:
    from .websocket_connector import WebSocketConnector
except ImportError:
    pass

try:
    from .rest_sync_connector import RESTSyncConnector
except ImportError:
    pass

try:
    from .rest_async_connector import RESTAsyncConnector
except ImportError:
    pass

# Service-specific connectors
try:
    from .simulation_connector import SimulationConnector
except ImportError:
    pass

try:
    from .comfyui_connector import ComfyUIConnector
except ImportError:
    pass

# Define what's available for import from this package
__all__ = [
    # Base connectors
    'WebSocketConnector',
    'RESTSyncConnector',
    'RESTAsyncConnector',
    
    # Service-specific connectors
    'SimulationConnector',
    'ComfyUIConnector'
]
