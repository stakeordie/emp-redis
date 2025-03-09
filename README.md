# EmProps Redis System

A distributed job queue and worker system built on Redis pub/sub.

## Repository Structure

This repository is organized as a monorepo with the following components:

- **core/**: Shared core modules for Redis communication and WebSocket handling
  - **client-types/**: TypeScript type definitions for client-server messages and interactions
- **hub/**: Redis Hub service that manages job distribution and worker communication
- **worker/**: Worker service that processes jobs
- **apps/**: Application-specific implementations
  - **redis-monitor/**: A monitoring dashboard for the Redis system
  - **mock-env/**: Development environment for testing

## Getting Started

### Development Setup

1. Clone this repository with all submodules:
   ```bash
   git clone --recursive https://github.com/yourusername/emp-redis.git
   ```

2. If you've already cloned the repository without `--recursive`, initialize and update the submodules:
   ```bash
   git submodule init
   git submodule update
   ```

3. Set up the development environment using the mock-env

### Running the Services

Each service can be run independently:

- Hub: `cd hub && python main.py`
- Worker: `cd worker && python main.py`

Alternatively, you can use the mock environment to run all services together:

```bash
cd apps/mock-env
docker-compose up
```

## Architecture

The system uses Redis pub/sub for real-time communication between components:

- The **Hub** manages job distribution and worker status through a WebSocket server on port 8001
- **Workers** connect directly to the Hub to receive and process jobs
- **Client applications** connect directly to the Hub's WebSocket server on port 8001 for monitoring and job submission
- The **Redis Monitor** provides a dashboard for monitoring the system in real-time

## License

[Your License Here]
