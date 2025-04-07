# EmProps Redis Worker Connectors
# Created: 2025-04-07T10:27:45-04:00

This directory contains connector implementations for the EmProps Redis Worker. Connectors allow the worker to communicate with various external services through different protocols.

## Available Connector Types

The worker supports three types of connectors:

1. **WebSocket Connectors** (`websocket_connector.py`)
   - For services that use WebSockets for real-time communication
   - Example: ComfyUI connector

2. **Synchronous REST Connectors** (`rest_sync_connector.py`)
   - For services that use REST APIs with immediate responses
   - Good for services where requests complete quickly

3. **Asynchronous REST Connectors** (`rest_async_connector.py`)
   - For services that use REST APIs with a job submission pattern
   - Submit a job, get a job ID, poll for completion, retrieve results

## Creating a New Connector

### Step 1: Choose the Right Base Connector

Choose the appropriate base connector based on how the external service communicates:

- Use `WebSocketConnector` for services that use WebSockets
- Use `RESTSyncConnector` for services with synchronous REST APIs
- Use `RESTAsyncConnector` for services with asynchronous job-based REST APIs

### Step 2: Create a New Connector Class

Create a new file in the `connectors` directory named after your service (e.g., `a1111_connector.py`):

```python
#!/usr/bin/env python3
# A1111 connector for the EmProps Redis Worker
import os
import json
import asyncio
import aiohttp
from typing import Dict, Any, Optional, Union, Callable

import sys
import os

# Add the parent directory to the Python path
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, parent_dir)

# Add the worker directory to the Python path
worker_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, worker_dir)

# Import the appropriate base connector
from worker.connectors.rest_sync_connector import RESTSyncConnector
# or
# from worker.connectors.rest_async_connector import RESTAsyncConnector
# or
# from worker.connectors.websocket_connector import WebSocketConnector

from core.utils.logger import logger

class A1111Connector(RESTSyncConnector):  # Or RESTAsyncConnector or WebSocketConnector
    """Connector for A1111 Stable Diffusion Web UI"""
    
    # Version identifier to verify code deployment
    VERSION = "2025-04-07-10:27-initial-implementation"
    
    def __init__(self):
        """Initialize the A1111 connector"""
        super().__init__()
        
        # Override default settings with A1111-specific settings
        self.job_type = os.environ.get("WORKER_A1111_JOB_TYPE", os.environ.get("A1111_JOB_TYPE", "a1111"))
        
        # Log configuration
        logger.info(f"[a1111_connector.py __init__] Initialized A1111 connector")
        
    # Implement required methods based on the base connector
    # ...
```

### Step 3: Implement Required Methods

#### For WebSocket Connectors:

```python
async def _on_connect(self) -> None:
    """Handle service-specific connection steps"""
    # Initialize service-specific connection details
    pass

async def _monitor_service_progress(self, job_id: str, send_progress_update: Callable) -> Dict[str, Any]:
    """Service-specific implementation of progress monitoring"""
    # Monitor progress and return results
    pass

async def _process_service_job(self, websocket, job_id: str, payload: Dict[str, Any], send_progress_update) -> Dict[str, Any]:
    """Service-specific implementation of job processing"""
    # Process the job and return results
    pass
```

#### For Synchronous REST Connectors:

The base implementation should work for most cases, but you can override methods as needed:

```python
def get_capabilities(self) -> Dict[str, Any]:
    """Get connector-specific capabilities"""
    capabilities = super().get_capabilities()
    capabilities.update({
        "a1111_version": "1.0.0",
        "supports_txt2img": True,
        "supports_img2img": True
    })
    return capabilities
```

#### For Asynchronous REST Connectors:

```python
def get_submit_endpoint(self) -> str:
    """Return the endpoint for job submission"""
    return "/sdapi/v1/txt2img"  # A1111-specific endpoint

def get_status_endpoint(self, job_id: str) -> str:
    """Return the endpoint for checking job status"""
    return f"/sdapi/v1/progress?id={job_id}"  # A1111-specific endpoint

def get_result_endpoint(self, job_id: str) -> str:
    """Return the endpoint for retrieving results"""
    return f"/sdapi/v1/result/{job_id}"  # A1111-specific endpoint

def parse_job_id_from_response(self, response: Dict[str, Any]) -> Optional[str]:
    """Extract job ID from submission response"""
    # A1111-specific job ID extraction
    return response.get("id")

def parse_status_from_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
    """Extract status from status response"""
    # A1111-specific status parsing
    progress = response.get("progress", 0)
    eta = response.get("eta_relative", 0)
    
    return {
        "status": "processing" if progress < 1.0 else "completed",
        "progress": int(progress * 100),
        "eta": eta,
        "message": f"Progress: {int(progress * 100)}%, ETA: {eta:.1f}s"
    }
```

### Step 4: Register the Connector

Add your connector to the `CONNECTORS` environment variable:

```
CONNECTORS=simulation,comfyui,a1111
```

Or add it to the `.env` file:

```
CONNECTORS=simulation,comfyui,a1111
```

## Environment Variables

Each connector type supports specific environment variables for configuration:

### WebSocket Connector

```
WORKER_SERVICE_HOST=localhost
WORKER_SERVICE_PORT=8188
WORKER_SERVICE_USE_SSL=false
WORKER_SERVICE_USERNAME=
WORKER_SERVICE_PASSWORD=
```

### Synchronous REST Connector

```
WORKER_REST_BASE_URL=http://localhost:8000
WORKER_REST_ENDPOINT=/api/process
WORKER_REST_USE_SSL=false
WORKER_REST_TIMEOUT=60
WORKER_REST_JOB_TYPE=rest
WORKER_REST_API_KEY=
WORKER_REST_USERNAME=
WORKER_REST_PASSWORD=
```

### Asynchronous REST Connector

```
WORKER_REST_ASYNC_BASE_URL=http://localhost:8000
WORKER_REST_ASYNC_SUBMIT_ENDPOINT=/api/submit
WORKER_REST_ASYNC_STATUS_ENDPOINT=/api/status/{job_id}
WORKER_REST_ASYNC_RESULT_ENDPOINT=/api/result/{job_id}
WORKER_REST_ASYNC_USE_SSL=false
WORKER_REST_ASYNC_TIMEOUT=300
WORKER_REST_ASYNC_POLL_INTERVAL=2.0
WORKER_REST_ASYNC_JOB_TYPE=rest_async
WORKER_REST_ASYNC_API_KEY=
WORKER_REST_ASYNC_USERNAME=
WORKER_REST_ASYNC_PASSWORD=
```

Replace `SERVICE` with your service name (e.g., `A1111`).

## Best Practices

1. **Error Handling**: Always use try/except blocks and provide detailed error messages
2. **Logging**: Use the logger with appropriate log levels and include the connector name in log messages
3. **Progress Updates**: Send regular progress updates to keep the client informed
4. **Resource Cleanup**: Always clean up resources in finally blocks and implement shutdown() properly
5. **Configuration**: Support both namespaced and non-namespaced environment variables
6. **Documentation**: Document all methods and configuration options
7. **Type Annotations**: Use proper type annotations for all methods and variables
8. **Version Tracking**: Include a VERSION constant and log it during initialization

## Testing

To test your connector, run the worker with your connector enabled:

```bash
cd worker
CONNECTORS=your_connector python main.py
```

Or use the test script:

```bash
cd worker
python test_connector_details.py your_connector
```
