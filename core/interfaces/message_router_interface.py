#!/usr/bin/env python3
# Interface for message routing
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable, Awaitable
from fastapi import WebSocket

class MessageRouterInterface(ABC):
    """
    Interface defining the contract for message routing.
    
    This interface ensures that all message routers follow the same
    contract, making it easier to implement different routers for
    different message types or sources.
    """
    
    @abstractmethod
    async def route_message(self, websocket: WebSocket, message: Dict[str, Any], 
                          connection_id: str) -> Optional[Dict[str, Any]]:
        """
        Route an incoming message to the appropriate handler.
        
        Args:
            websocket: WebSocket connection that received the message
            message: Message data
            connection_id: ID of the connection (client_id, worker_id, etc.)
            
        Returns:
            Optional[Dict[str, Any]]: Optional response message
        """
        pass
    
    @abstractmethod
    def register_route(self, message_type: str, 
                      handler: Callable[[WebSocket, Dict[str, Any], str], Awaitable[Optional[Dict[str, Any]]]]) -> None:
        """
        Register a route (handler function) for a specific message type.
        
        Args:
            message_type: Type of message to route
            handler: Handler function that takes (websocket, message, connection_id) and returns a response
        """
        pass
    
    @abstractmethod
    def get_route(self, message_type: str) -> Optional[Callable[[WebSocket, Dict[str, Any], str], Awaitable[Optional[Dict[str, Any]]]]]:
        """
        Get the route (handler function) for a specific message type.
        
        Args:
            message_type: Type of message to get route for
            
        Returns:
            Optional[Callable]: Handler function if registered, None otherwise
        """
        pass
