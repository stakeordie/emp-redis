#!/bin/bash
# Docker entrypoint script for the worker
# Updated: 2025-04-07T11:34:00-04:00 - Updated to work with new directory structure

# Print current directory
echo "[docker_entrypoint.sh] Current directory: $(pwd)"
echo "[docker_entrypoint.sh] Directory contents:"
ls -la

# Navigate to the worker directory in the new structure
if [ -d "emp-redis-worker/worker" ]; then
    echo "[docker_entrypoint.sh] Found emp-redis-worker/worker directory, changing to it"
    cd emp-redis-worker/worker
    echo "[docker_entrypoint.sh] New current directory: $(pwd)"
    echo "[docker_entrypoint.sh] New directory contents:"
    ls -la
fi

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

# Run the worker using worker_main.py at the root level
echo "[docker_entrypoint.sh] Starting worker using worker_main.py..."

# Check if we're in the emp-redis-worker directory structure
if [ -f "../worker_main.py" ]; then
    echo "[docker_entrypoint.sh] Found worker_main.py in parent directory, using it"
    cd ..
    echo "[docker_entrypoint.sh] Changed to directory: $(pwd)"
    echo "[docker_entrypoint.sh] Directory contents:"
    ls -la
    python worker_main.py
else
    # Fallback to the old approach if worker_main.py is not found
    echo "[docker_entrypoint.sh] worker_main.py not found, falling back to worker.py"
    python worker.py
fi
