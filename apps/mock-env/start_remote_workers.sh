#!/bin/bash

# Script to start workers that connect to the remote Redis Hub on Railway

# Default values
AUTH_TOKEN="your-secure-token-here"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --token=*)
      AUTH_TOKEN="${1#*=}"
      shift
      ;;
    *)
      echo "Unknown parameter: $1"
      echo "Usage: $0 [--token=TOKEN]"
      exit 1
      ;;
  esac
done

# Update the auth token in the docker-compose file
sed -i '' "s/WEBSOCKET_AUTH_TOKEN=.*/WEBSOCKET_AUTH_TOKEN=$AUTH_TOKEN/g" docker-compose.remote.yml

# Start the workers with the remote profile
echo "Starting workers connecting to redisserver-production.up.railway.app"
docker-compose -f docker-compose.remote.yml --profile remote up -d --build

echo "Workers started. View logs with:"
echo "docker-compose -f docker-compose.remote.yml logs -f"
