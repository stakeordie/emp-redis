# EmProps Redis Mock Environment

This directory contains a Docker Compose setup for running a complete mock environment of the EmProps Redis system. This environment includes the Hub and Worker components configured to work together.

## Components

The mock environment includes the following services:

- **Hub**: Central Redis service with both Redis DB and WebSocket server on port 8001
- **Worker1**: Worker service with 1 worker process
- **Worker2**: Worker service with 4 worker processes

## Usage

To start the mock environment:

```bash
# Navigate to the mock environment directory
cd apps/mock-env

# Start all services
docker-compose up

# Alternatively, run in detached mode
docker-compose up -d
```

## Service Endpoints

- Hub WebSocket: ws://localhost:8001
- Redis DB: localhost:6380

## Architecture

This mock environment builds containers directly from the repository:

1. The Hub service provides both Redis database functionality and a WebSocket server on port 8001
2. Worker services connect directly to the Hub's WebSocket server
3. Client applications connect directly to the Hub's WebSocket server on port 8001
4. The core module is copied into each container to provide shared functionality

This approach mirrors how the services would be deployed in production, without using volume mounts for development.

## Troubleshooting

If you encounter issues with the mock environment:

1. Check the logs for each service: `docker-compose logs [service_name]`
2. Ensure all submodules are properly initialized: `git submodule update --init --recursive`
3. Rebuild the containers if needed: `docker-compose build --no-cache`
