#!/bin/bash
# Script to build and push the Redis Server Docker image

# Set variables
IMAGE_NAME="emprops/redis_server"
TAG="latest"
DOCKERFILE_PATH="./apps/prod_redis_server/Dockerfile"

# Build the Docker image for Linux/AMD64 platform
echo "Building Docker image for linux/amd64: $IMAGE_NAME:$TAG"
docker buildx build --platform linux/amd64 --push -t $IMAGE_NAME:$TAG -f $DOCKERFILE_PATH .

# Check if build was successful
if [ $? -ne 0 ]; then
    echo "Error: Docker build failed"
    exit 1
fi

echo "Docker image built successfully: $IMAGE_NAME:$TAG"

echo "Done!"
