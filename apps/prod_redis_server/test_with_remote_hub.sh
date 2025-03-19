#!/bin/bash

# Script to test workers with a remote production hub

# Default values
HUB_HOST="redisserver-production.up.railway.app"
HUB_PORT="443"
AUTH_TOKEN="your-secure-token-here"
WORKER_COUNT=2
USE_SSL=true

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --host=*)
      HUB_HOST="${1#*=}"
      shift
      ;;
    --port=*)
      HUB_PORT="${1#*=}"
      shift
      ;;
    --token=*)
      AUTH_TOKEN="${1#*=}"
      shift
      ;;
    --workers=*)
      WORKER_COUNT="${1#*=}"
      shift
      ;;
    --no-ssl)
      USE_SSL=false
      shift
      ;;
    *)
      echo "Unknown parameter: $1"
      echo "Usage: $0 [--host=HOST] [--port=PORT] [--token=TOKEN] [--workers=COUNT] [--no-ssl]"
      exit 1
      ;;
  esac
done

# Create a temporary docker-compose file with the specified hub host
cat > docker-compose.remote.yml << EOF
version: '3.8'

services:
EOF

# Add the specified number of worker services
for i in $(seq 1 $WORKER_COUNT); do
  cat >> docker-compose.remote.yml << EOF
  worker$i:
    container_name: remote-worker$i
    build:
      context: ../../
      dockerfile: ./apps/prod_redis_server/Dockerfile.worker
    environment:
      - REDIS_API_HOST=$HUB_HOST
      - REDIS_API_PORT=$HUB_PORT
      - WORKER_ID=remote-worker$i
      - WEBSOCKET_AUTH_TOKEN=$AUTH_TOKEN
      - PYTHONPATH=/app
      - USE_SSL=$USE_SSL
    restart: unless-stopped
EOF
done

# Start the workers
echo "Starting $WORKER_COUNT workers connecting to $HUB_HOST:$HUB_PORT"
docker-compose -f docker-compose.remote.yml up -d --build

echo "Workers started. View logs with:"
echo "docker-compose -f docker-compose.remote.yml logs -f"
