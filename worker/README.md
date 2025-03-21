# EmProps Redis Worker

Modular worker service for the EmProps Redis system.

## Overview

The Worker component connects to the Redis Hub and processes jobs from the queue. It uses a modular connector-based architecture that allows different job types to be processed by specialized connectors.

## Features

- WebSocket connection to the Hub
- Job processing and status reporting
- Heartbeat mechanism for worker status tracking
- Modular connector-based architecture
- Configurable worker capabilities

## Architecture

The worker consists of the following components:

- **BaseWorker**: Core worker class that handles communication with the Redis Hub
- **Connectors**: Specialized modules that handle specific job types
- **ConnectorInterface**: Interface that all connectors must implement

## Configuration

Configuration is done through environment variables. You can create a `.env` file in the worker directory based on the provided `.env.example` file.

Key configuration options:

- `REDIS_API_HOST` and `REDIS_API_PORT`: Redis Hub connection details
- `WORKER_ID`: Unique identifier for this worker
- `CONNECTORS`: Comma-separated list of connectors to load
- Connector-specific environment variables (prefixed with connector name)

## Running

To run the Worker service:

```bash
python worker.py
```

## Connectors

Connectors are specialized modules that handle specific job types. Each connector must implement the `ConnectorInterface` and be located in the `connectors/` directory.

Available connectors:

- **Simulation Connector**: Simulates job processing for testing purposes
- **ComfyUI Connector**: Processes ComfyUI workflow jobs

### Creating a New Connector

To create a new connector:

1. Create a new file in the `connectors/` directory named `[connector_name]_connector.py`
2. Implement the `ConnectorInterface` class
3. Add connector-specific environment variables to `.env` with the prefix `[CONNECTOR_NAME]_`
4. Add the connector name to the `CONNECTORS` environment variable

## Development

The Worker service uses the core modules for its functionality. When making changes, ensure compatibility with the Hub service.

### Testing

You can test the worker with the simulation connector by setting:

```
CONNECTORS=simulation
```

This will simulate job processing without requiring external services.
