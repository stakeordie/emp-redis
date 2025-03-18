#!/usr/bin/env python3
# Interface for WebSocket connection management
from abc import ABC, abstractmethod
from typing import Dict, Set, List, Any, Optional, Callable
from fastapi import WebSocket

# Import BaseMessage for type annotations
from ..core_types.base_messages import BaseMessage

class ConnectionManagerInterface(ABC):
    """
    Interface defining the contract for WebSocket connection management.
    
    This interface ensures that all implementations of the connection manager
    follow the same contract, making it easier to swap implementations
    or create mock versions for testing.
    """
    
    @abstractmethod
    async def connect_client(self, websocket: WebSocket, client_id: str) -> None:
        """
        Connect a client WebSocket.
        
        Args:
            websocket: WebSocket connection
            client_id: Unique identifier for the client
        """
        pass
    
    @abstractmethod
    async def connect_worker(self, websocket: WebSocket, worker_id: str) -> None:
        """
        Connect a worker WebSocket.
        
        Args:
            websocket: WebSocket connection
            worker_id: Unique identifier for the worker
        """
        pass
    
    @abstractmethod
    async def connect_monitor(self, websocket: WebSocket, monitor_id: str) -> None:
        """
        Connect a monitor WebSocket.
        
        Args:
            websocket: WebSocket connection
            monitor_id: Unique identifier for the monitor
        """
        pass
    
    @abstractmethod
    def disconnect_client(self, client_id: str) -> None:
        """
        Disconnect a client.
        
        Args:
            client_id: ID of the client to disconnect
        """
        pass
    
    @abstractmethod
    async def disconnect_worker(self, worker_id: str) -> None:
        """
        Disconnect a worker.
        
        Args:
            worker_id: ID of the worker to disconnect
        """
        pass
    
    @abstractmethod
    def disconnect_monitor(self, monitor_id: str) -> None:
        """
        Disconnect a monitor.
        
        Args:
            monitor_id: ID of the monitor to disconnect
        """
        pass
    
    @abstractmethod
    async def send_to_client(self, client_id: str, message: BaseMessage) -> bool:
        """
        Send a message to a specific client.
        
        Args:
            client_id: ID of the client to send the message to
            message: Message to send as a BaseMessage object
            
        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        # Note: This method now only accepts BaseMessage objects to ensure type consistency
        # All message objects in the system should inherit from BaseMessage
        pass
    
    @abstractmethod
    async def send_to_worker(self, worker_id: str, message: BaseMessage) -> bool:
        """
        Send a message to a specific worker.
        
        Args:
            worker_id: ID of the worker to send the message to
            message: Message to send as a BaseMessage object
            
        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        # Note: This method now only accepts BaseMessage objects to ensure type consistency
        # All message objects in the system should inherit from BaseMessage
        pass
    
    @abstractmethod
    async def send_to_monitor(self, monitor_id: str, message: BaseMessage) -> bool:
        """
        Send a message to a specific monitor.
        
        Args:
            monitor_id: ID of the monitor to send the message to
            message: Message to send as a BaseMessage object
            
        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        # Note: This method now only accepts BaseMessage objects to ensure type consistency
        # All message objects in the system should inherit from BaseMessage
        pass
    
    @abstractmethod
    async def broadcast_to_clients(self, message: BaseMessage) -> int:
        """
        Broadcast a message to all connected clients.
        
        Args:
            message: Message to broadcast as a BaseMessage object
            
        Returns:
            int: Number of clients the message was successfully sent to
        """
        # Note: This method now only accepts BaseMessage objects to ensure type consistency
        # All message objects in the system should inherit from BaseMessage
        pass
    
    @abstractmethod
    async def broadcast_to_workers(self, message: BaseMessage) -> int:
        """
        Broadcast a message to all connected workers.
        
        Args:
            message: Message to broadcast as a BaseMessage object
            
        Returns:
            int: Number of workers the message was successfully sent to
        """
        # Note: This method now only accepts BaseMessage objects to ensure type consistency
        # All message objects in the system should inherit from BaseMessage
        pass
    
    @abstractmethod
    async def broadcast_to_monitors(self, message: BaseMessage) -> int:
        """
        Broadcast a message to all connected monitors.
        
        Args:
            message: Message to broadcast as a BaseMessage object
            
        Returns:
            int: Number of monitors the message was successfully sent to
        """
        # Note: This method now only accepts BaseMessage objects to ensure type consistency
        # All message objects in the system should inherit from BaseMessage
        pass
    
    @abstractmethod
    async def broadcast_stats(self, stats: BaseMessage) -> int:
        """
        Broadcast statistics to all subscribed clients.
        
        Args:
            stats: Statistics data to broadcast as a BaseMessage object (e.g., StatsResponseMessage)
            
        Returns:
            int: Number of clients the stats were successfully sent to
        """
        # Note: This method now only accepts BaseMessage objects to ensure type consistency
        # All message objects in the system should inherit from BaseMessage
        pass
    
    @abstractmethod
    async def subscribe_to_job(self, client_id: str, job_id: str) -> bool:
        """
        Subscribe a client to job updates.
        
        Args:
            client_id: ID of the client subscribing
            job_id: ID of the job to subscribe to
            
        Returns:
            bool: True if subscription was successful, False otherwise
        """
        pass
    
    @abstractmethod
    def subscribe_to_stats(self, client_id: str) -> None:
        """
        Subscribe a client to system statistics updates.
        
        Args:
            client_id: ID of the client subscribing
        """
        pass
    
    @abstractmethod
    async def subscribe_to_job_notifications(self, worker_id: str, enabled: bool = True) -> bool:
        """
        Subscribe a worker to job notifications.
        
        Args:
            worker_id: ID of the worker subscribing
            enabled: Whether to enable or disable the subscription
            
        Returns:
            bool: True if subscription was successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def notify_job_update(self, job_id: str, update: Dict[str, Any]) -> bool:
        """
        Notify subscribers about a job update.
        
        Args:
            job_id: ID of the job that was updated
            update: Update data
            
        Returns:
            bool: True if update was sent successfully, False otherwise
        """
        pass
