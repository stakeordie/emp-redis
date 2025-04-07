#!/usr/bin/env python3
# EmProps Redis Worker Package
# Created: 2025-04-07T11:12:00-04:00
# Updated: 2025-04-07T11:12:00-04:00

"""
EmProps Redis Worker package.

This package contains the worker implementation for the EmProps Redis system.
It handles job processing, connector management, and communication with the Redis hub.
"""

# Make core components available at the package level
# This allows imports like: from worker import ConnectorInterface

# Core interfaces
try:
    from .connector_interface import ConnectorInterface
except ImportError:
    pass

# Worker components
try:
    # Import Worker from worker.py and BaseWorker from base_worker.py
    from .worker import log_environment_info, main as worker_main
    from .base_worker import BaseWorker
    from .connector_loader import load_connectors, get_supported_job_types, get_worker_capabilities
except ImportError as e:
    import sys
    print(f"Error importing worker components: {e}", file=sys.stderr)

# Import connectors package to make it available
try:
    from . import connectors
except ImportError:
    pass

__all__ = [
    'ConnectorInterface',
    'BaseWorker',
    'worker_main',
    'log_environment_info',
    'load_connectors',
    'get_supported_job_types',
    'get_worker_capabilities',
    'connectors'
]