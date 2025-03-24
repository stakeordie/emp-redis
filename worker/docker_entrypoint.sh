#!/bin/bash
# Docker entrypoint script for the worker

# Print current directory
echo "[docker_entrypoint.sh] Current directory: $(pwd)"
echo "[docker_entrypoint.sh] Directory contents:"
ls -la

# Check if .env file exists, if not, copy from .env.example
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    echo "Creating .env from .env.example"
    cp .env.example .env
fi

# Print environment information
echo "[docker_entrypoint.sh] Environment information:"
echo "[docker_entrypoint.sh] REDIS_API_HOST: ${REDIS_API_HOST:-not set}"
echo "[docker_entrypoint.sh] REDIS_API_PORT: ${REDIS_API_PORT:-not set}"
echo "[docker_entrypoint.sh] USE_SSL: ${USE_SSL:-not set}"
echo "[docker_entrypoint.sh] WORKER_ID: ${WORKER_ID:-not set}"
echo "[docker_entrypoint.sh] CONNECTORS: ${CONNECTORS:-not set}"

# Run the worker
echo "[docker_entrypoint.sh] Starting worker..."
python worker.py
