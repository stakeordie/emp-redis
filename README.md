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

3. Install the required Python dependencies:
   ```bash
   pip install python-dotenv redis aioredis fastapi uvicorn websockets
   ```

4. Configure the environment variables by editing the `.env` file in the root directory.

### Environment Configuration

The system uses `.env` files for configuration. The following `.env` files are provided:

- **Root `.env`**: Used when running services directly (without Docker)
- **`hub/.env`**: Used when running the hub service
- **`worker/.env`**: Used when running the worker service

#### Redis Connection Configuration

The system now uses a Redis URL format for connecting to Redis servers, which simplifies configuration and makes it easy to switch between local and remote Redis instances.

**Local Redis Connection:**
```
REDIS_URL=redis://localhost:6379/0
```

**Remote Redis Connection:**
```
REDIS_URL=redis://username:password@your-remote-redis-host:port/db
```

**Example with Railway.app Redis:**
```
REDIS_URL=redis://default:password@gondola.proxy.rlwy.net:36565
```

#### Connection URL Format

The Redis URL follows this format:
```
redis://[[username]:[password]@][host][:port][/database]
```

Where:
- `username`: Optional Redis username (if authentication is enabled)
- `password`: Optional Redis password (if authentication is enabled)
- `host`: Redis server hostname or IP address
- `port`: Redis server port (default: 6379)
- `database`: Redis database number (default: 0)

### Running the Services

Each service can be run independently:

- Hub: `cd hub && python main.py`
- Worker: `cd worker && python main.py`

#### Docker Deployment

You can use Docker Compose to run all services together:

```bash
cd apps/mock-env
docker-compose up
```

The Docker setup automatically copies the `.env` files from the hub and worker directories to the respective containers. To switch between local and remote Redis servers when using Docker, update the `REDIS_URL` in both `hub/.env` and `worker/.env` files.

## Architecture

The system uses Redis pub/sub for real-time communication between components:

- The **Hub** manages job distribution and worker status through a WebSocket server on port 8001
- **Workers** connect directly to the Hub to receive and process jobs
- **Client applications** connect directly to the Hub's WebSocket server on port 8001 for monitoring and job submission
- The **Redis Monitor** provides a dashboard for monitoring the system in real-time

## License

[Your License Here]
