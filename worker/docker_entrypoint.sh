#!/bin/bash
# Docker entrypoint script for the worker

# Print current directory
echo "Current directory: $(pwd)"
echo "Directory contents:"
ls -la

# Check if .env file exists, if not, copy from .env.example
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    echo "Creating .env from .env.example"
    cp .env.example .env
fi

# Print environment information
echo "Environment information:"
echo "REDIS_API_HOST: ${REDIS_API_HOST:-not set}"
echo "REDIS_API_PORT: ${REDIS_API_PORT:-not set}"
echo "USE_SSL: ${USE_SSL:-not set}"
echo "WORKER_ID: ${WORKER_ID:-not set}"
echo "CONNECTORS: ${CONNECTORS:-not set}"

# Run the worker
echo "Starting worker..."
python worker.py
