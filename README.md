# EmProps Redis System

A distributed job queue and worker system built on Redis pub/sub.

## Repository Structure

This repository is organized as a monorepo with the following Git submodules:

- **core/**: Shared core modules for Redis communication and WebSocket handling
- **hub/**: Redis Hub service that manages job distribution and worker communication
- **worker/**: Worker service that processes jobs
- **api/**: API service that provides a frontend interface
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
- API: `cd api && python main.py`

## Architecture

The system uses Redis pub/sub for real-time communication between components:

- The Hub manages job distribution and worker status
- Workers connect to the Hub to receive and process jobs
- The API provides a frontend interface for monitoring and job submission

## License

[Your License Here]
