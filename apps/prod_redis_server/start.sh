#!/bin/bash
# Only enable debug mode if DEBUG is set
if [ "${DEBUG:-}" = "true" ]; then
    set -x
fi

# Start Redis server
service redis-server start

# Start the FastAPI application
exec python -m uvicorn main:app --host 0.0.0.0 --port ${API_PORT}
