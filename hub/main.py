#!/usr/bin/env python3
# Main entry point for the core WebSocket-based Queue API
import os
import asyncio
import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager

import sys
import os

# Add parent directory to path to find core module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.message_broker import MessageBroker
from core.redis_service import RedisService

from core.utils.logger import logger

logger.info("IT WORKS")

# FastAPI startup and shutdown event handling
@asynccontextmanager
async def lifespan(app: FastAPI):
    
    # Create MessageBroker instance with all required components
    message_broker = MessageBroker()
    
    # Initialize WebSocket connections
    message_broker.init_connections(app)
    
    # Start background tasks (including Redis pub/sub listener)
    await message_broker.start_background_tasks()
    
    yield
    
    # Shutdown tasks
    try:
        await message_broker.stop_background_tasks()
    except asyncio.CancelledError:
        pass
    
    # Close Redis connections
    redis_service = RedisService()
    await redis_service.close_async()

# Initialize FastAPI with lifespan manager
app = FastAPI(title="WebSocket Queue API", lifespan=lifespan)

@app.get("/")
def read_root():
    """Root endpoint for health check"""
    return {"status": "ok", "message": "WebSocket Queue API is running"}

# Run the application
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=False)
