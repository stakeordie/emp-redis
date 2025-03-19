# EmProps Redis Modular Worker

This is a modular worker architecture for the EmProps Redis system that allows for pluggable service connectors.

## Features

- Modular architecture with pluggable service connectors
- Dynamic loading of connectors based on configuration
- Each connector handles a specific job type
- WebSocket connection to the Redis Hub
- Automatic registration of capabilities based on loaded connectors

## Architecture

The modular worker consists of the following components:

- **Base Worker**: Handles core functionality like connecting to Redis Hub, claiming jobs, and reporting progress
- **Connector Interface**: Defines the interface that all service connectors must implement
- **Connector Loader**: Loads connectors based on configuration
- **Service Connectors**: Implement specific job processing logic for different services

## Available Connectors

- **ComfyUI Connector**: Connects to ComfyUI for processing workflows
- **Simulation Connector**: Simulates job processing for testing

## Setup

1. Copy `.env.example` to `.env`:
   ```
   cp .env.example .env
   ```

2. Configure the environment variables in `.env`:
   - Set `REDIS_API_HOST` to your Redis Hub hostname
   - Set `REDIS_API_PORT` to your Redis Hub port
   - Set `USE_SSL` to true if connecting to Railway
   - Set `WORKER_ID` to a unique identifier for this worker
   - Set `WEBSOCKET_AUTH_TOKEN` to match the token configured on the Redis Hub
   - Set `CONNECTORS` to a comma-separated list of connectors to load

3. Configure connector-specific settings:
   - Copy connector-specific `.env` files:
     ```
     cp .env.comfyui .env.comfyui.local
     cp .env.simulation .env.simulation.local
     ```
   - Modify the connector-specific settings as needed

4. Run the worker:
   ```
   python worker/worker.py
   ```

## Creating a New Connector

To create a new connector:

1. Create a new file in the `connectors` directory named `<connector_name>_connector.py`
2. Implement the `ConnectorInterface` class
3. Create a connector-specific `.env` file with configuration options
4. Add the connector name to the `CONNECTORS` list in the main `.env` file

Example connector implementation:

```python
from connector_interface import ConnectorInterface
from core.utils.logger import logger

class MyConnector(ConnectorInterface):
    def __init__(self):
        # Initialize connector with configuration from environment variables
        pass
    
    def initialize(self) -> bool:
        # Initialize the connector
        return True
    
    def get_job_type(self) -> str:
        # Return the job type this connector handles
        return "my_job_type"
    
    def get_capabilities(self) -> Dict[str, Any]:
        # Return connector-specific capabilities
        return {"my_capability": "value"}
    
    async def process_job(self, websocket, job_id, payload, send_progress_update) -> Dict[str, Any]:
        # Process a job
        return {"status": "success", "output": {}}
    
    async def shutdown(self) -> None:
        # Clean up resources
        pass
```

## Job Processing Flow

1. Worker connects to Redis Hub and registers capabilities
2. Redis Hub sends job notifications to the worker
3. Worker claims a job and receives job details
4. Worker finds the appropriate connector for the job type
5. Connector processes the job and reports progress
6. Worker sends job completion message to Redis Hub

## Troubleshooting

- If the worker fails to connect to the Redis Hub, check the `REDIS_API_HOST`, `REDIS_API_PORT`, and `WEBSOCKET_AUTH_TOKEN` settings.
- If a connector fails to initialize, check the connector-specific configuration.
- Check the logs for detailed error messages.
