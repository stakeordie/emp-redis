FROM python:3.10-slim

WORKDIR /app

# Install Redis and Python dependencies
RUN apt-get update && \
    apt-get install -y redis-server && \
    pip install --no-cache-dir fastapi uvicorn websockets aioredis redis python-dotenv

# Copy Hub code and core code
COPY ./hub /app/
COPY ./core /app/core/

# Create a directory for environment configuration
RUN mkdir -p /app/config

# Ensure Python can find the core modules
ENV PYTHONPATH=/app

# Expose Redis and API ports
EXPOSE 6379 8001

# Start Redis and the FastAPI server
CMD service redis-server start && python -m uvicorn main:app --host 0.0.0.0 --port 8001
