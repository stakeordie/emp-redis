FROM python:3.10-slim

WORKDIR /app

# Install Redis and Python dependencies
RUN apt-get update && \
    apt-get install -y redis-server && \
    pip install --no-cache-dir fastapi uvicorn websockets aioredis redis python-dotenv pydantic

# Copy Hub code and core code
COPY ./hub /app/
COPY ./core /app/core/

# Create a startup script directly in the container
COPY ./apps/prod_redis_server/start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Create a directory for environment configuration
RUN mkdir -p /app/config

# Ensure Python can find the core modules
ENV PYTHONPATH=/app

# Expose Redis and API ports
EXPOSE 6379 8001

# Set environment variables with default values
ENV REDIS_URL=redis://localhost:6379/0
ENV API_PORT=8001

# Copy .env file for additional configuration
COPY ./hub/.env /app/.env

# Start Redis and the FastAPI server
CMD ["/app/start.sh"]
