#!/usr/bin/env python3
# Interface for message handling
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from fastapi import FastAPI, WebSocket

# Import base message types for type safety
from ..core_types.base_messages import BaseMessage

class MessageHandlerInterface(ABC):
    """
    Interface defining the contract for handling  message types.
    
    This interface ensures that all  message handler implementations
    follow the same contract, making it easier to organize and
    maintain message handling logic.
    """
    
    @abstractmethod
    async def handle_client_message(self, client_id: str, 
                                  message_type: str,
                                  message_data: Dict[str, Any], 
                                  websocket: WebSocket) -> None:
        """
        Handle a message from a client.
        
        Args:
            client_id: Client identifier
            message_type: Type of message
            message_data: Message data
            websocket: WebSocket connection
        """
        pass
    
    @abstractmethod
    async def handle_worker_message(self, worker_id: str,
                                  message_type: str,
                                  message_data: Dict[str, Any], 
                                  websocket: WebSocket) -> None:
        """
        Handle a message from a worker.
        
        Args:
            worker_id: Worker identifier
            message_type: Type of message
            message_data: Message data
            websocket: WebSocket connection
        """
        pass
    
    @abstractmethod
    async def handle_monitor_message(self, monitor_id: str,
                                   message_type: str,
                                   message_data: Dict[str, Any], 
                                   websocket: WebSocket) -> None:
        """
        Handle a message from a monitor.
        
        Args:
            monitor_id: Monitor identifier
            message_type: Type of message
            message_data: Message data
            websocket: WebSocket connection
        """
        pass
    
    @abstractmethod
    async def handle_submit_job(self, client_id: str, message: Dict[str, Any]) -> None:
        """
        Handle job submission from a client.
        
        Args:
            client_id: Client identifier
            message: Submit job message
        """
        pass
    
    @abstractmethod
    async def handle_register_worker(self, worker_id: str, message: BaseMessage) -> None:
        """
        Handle worker registration.
        
        Args:
            worker_id: Worker identifier
            message: Register worker message
        """
        pass
