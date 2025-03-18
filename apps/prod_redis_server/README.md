# EmProps Redis Server - Production Deployment

This directory contains the production deployment configuration for the EmProps Redis Server.

## Quick Start

1. Copy the example environment file:
   ```
   cp config/.env.example config/.env
   ```

2. Edit the `.env` file as needed

3. Start the Redis Hub:
   ```
   docker-compose up -d
   ```

## Configuration

The Redis Hub is configured through environment variables in the `.env` file:

- `REDIS_URL`: The Redis connection URL (default: redis://localhost:6379/0)
- `REDIS_API_HOST`: The host to bind the API server to (default: 0.0.0.0)
- `REDIS_API_PORT`: The port for the API server (default: 8001)

## Connecting Workers

Workers should connect to the Redis Hub using:
- Host: Your server's IP or hostname
- Port: 8001 (or whatever you configured in REDIS_API_PORT)

## Data Persistence

Redis data is persisted in a Docker volume named `redis-data`.
