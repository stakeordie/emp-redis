#!/usr/bin/env python3
# Message Broker - Main entry point for message handling and connections

import asyncio
from typing import List, Dict, Set, Any, Optional
from fastapi import FastAPI, WebSocket

from .redis_service import RedisService
from .connection_manager import ConnectionManager
from .message_router import MessageRouter
from .message_models import MessageModels
from .message_handler import MessageHandler
from .utils.logger import logger

class MessageBroker:
    """
    Main entry point for message handling and connections.
    
    This class initializes all the components (RedisService, ConnectionManager, 
    MessageRouter, MessageHandler) and sets up the connections between them.
    """
    
    def __init__(self):
        """
        Initialize the MessageBroker with all required components.
        """
        # Initialize components
        self.redis_service = RedisService()
        
        self.connection_manager = ConnectionManager()
        self.message_router = MessageRouter()
        self.message_models = MessageModels()
        
        # Create MessageHandler with all dependencies
        self.message_handler = MessageHandler(
            redis_service=self.redis_service,
            connection_manager=self.connection_manager,
            message_router=self.message_router,
            message_models=self.message_models
        )
        
        # Set message_handler and redis_service in connection_manager for message delegation
        self.connection_manager.message_handler = self.message_handler
        self.connection_manager.redis_service = self.redis_service
        
        # Store background tasks
        self._background_tasks: List[asyncio.Task] = []
    
    def init_connections(self, app: FastAPI) -> None:
        """
        Initialize WebSocket connections for the FastAPI application.
        
        Args:
            app: FastAPI application instance
        """
        # Delegate to ConnectionManager for WebSocket route registration
        self.connection_manager.init_routes(app)
    
    async def start_background_tasks(self) -> None:
        """Start all background tasks"""
        # Start background tasks from MessageHandler
        await self.message_handler.start_background_tasks()
    
    async def stop_background_tasks(self) -> None:
        """Stop all background tasks"""
        # Stop background tasks from MessageHandler
        await self.message_handler.stop_background_tasks()
