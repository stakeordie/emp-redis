#!/usr/bin/env python3
# Interface for Redis service operations
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union, Callable

class RedisServiceInterface(ABC):
    """
    Interface defining the contract for Redis service operations.
    
    This interface ensures that all implementations of the Redis service
    follow the same contract, making it easier to swap implementations
    or create mock versions for testing.
    """
    
    @abstractmethod
    async def connect_async(self) -> None:
        """
        Connect to Redis asynchronously for pub/sub operations.
        
        This method should establish an asynchronous connection to Redis
        for operations that require pub/sub functionality.
        """
        pass
    
    @abstractmethod
    async def close_async(self) -> None:
        """
        Close the async Redis connection.
        
        This method should properly close the asynchronous Redis connection
        and clean up any resources.
        """
        pass
    
    @abstractmethod
    async def init_redis(self) -> bool:
        """
        Initialize Redis connections and data structures.
        
        This method ensures that both synchronous and asynchronous
        Redis connections are properly established and initializes
        any necessary data structures for the job queue system.
        
        Returns:
            bool: True if initialization was successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """
        Close all Redis connections.
        
        This method ensures that both synchronous and asynchronous
        Redis connections are properly closed and resources are released.
        """
        pass
    
    # Job operations
    @abstractmethod
    def add_job(self, job_id: str, job_type: str, priority: int, 
                params: Dict[str, Any], client_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Add a job to the queue.
        
        Args:
            job_id: Unique identifier for the job
            job_type: Type of job to be processed
            priority: Priority level (higher values = higher priority)
            params: Job parameters
            client_id: Optional client identifier
            
        Returns:
            Dict[str, Any]: Job data including position in queue
        """
        pass
    
    # get_next_job method removed - legacy code
    
    @abstractmethod
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of a job.
        
        Args:
            job_id: ID of the job to check
            
        Returns:
            Optional[Dict[str, Any]]: Job status data if job exists, None otherwise
        """
        pass
    
    @abstractmethod
    def update_job_progress(self, job_id: str, progress: int, 
                           message: Optional[str] = None) -> bool:
        """
        Update the progress of a job.
        
        Args:
            job_id: ID of the job to update
            progress: Progress percentage (0-100)
            message: Optional status message
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        pass
    
    @abstractmethod
    def complete_job(self, job_id: str, result: Optional[Dict[str, Any]] = None) -> bool:
        """
        Mark a job as completed.
        
        Args:
            job_id: ID of the job to complete
            result: Optional job result data
            
        Returns:
            bool: True if completion was successful, False otherwise
        """
        pass
    
    @abstractmethod
    def fail_job(self, job_id: str, error: str) -> bool:
        """
        Mark a job as failed.
        
        Args:
            job_id: ID of the job that failed
            error: Error message
            
        Returns:
            bool: True if failure was recorded successfully, False otherwise
        """
        pass
    
    # Worker operations
    @abstractmethod
    def register_worker(self, worker_id: str, capabilities: Optional[Dict[str, Any]] = None) -> bool:
        """
        Register a worker in the system.
        
        Args:
            worker_id: Unique identifier for the worker
            capabilities: Optional worker capabilities
            
        Returns:
            bool: True if registration was successful, False otherwise
        """
        pass
    
    @abstractmethod
    def update_worker_status(self, worker_id: str, status: str, 
                            job_id: Optional[str] = None) -> bool:
        """
        Update the status of a worker.
        
        Args:
            worker_id: ID of the worker to update
            status: New status (e.g., "idle", "busy")
            job_id: Optional ID of the job the worker is processing
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        pass
    
    @abstractmethod
    def worker_heartbeat(self, worker_id: str) -> bool:
        """
        Record a heartbeat from a worker.
        
        Args:
            worker_id: ID of the worker sending the heartbeat
            
        Returns:
            bool: True if heartbeat was recorded successfully, False otherwise
        """
        pass
    
    # Stats and monitoring
    @abstractmethod
    def request_stats(self) -> Dict[str, Any]:
        """
        Get system statistics.
        
        Returns:
            Dict[str, Any]: System statistics including queue lengths, job counts, etc.
        """
        pass
    
    @abstractmethod
    def cleanup_stale_jobs(self, max_heartbeat_age: int = 600) -> int:
        """
        Clean up stale jobs.
        
        Args:
            max_heartbeat_age: Maximum age in seconds for a worker heartbeat
            
        Returns:
            int: Number of jobs cleaned up
        """
        pass
    
    @abstractmethod
    def cleanup_stale_claims(self, max_claim_age: int = 30) -> int:
        """
        Clean up stale job claims.
        
        Args:
            max_claim_age: Maximum age in seconds for a job claim
            
        Returns:
            int: Number of claims cleaned up
        """
        pass
    
    @abstractmethod
    def notify_idle_workers_of_job(self, job_id: str, job_type: str, job_request_payload: Optional[str] = None) -> List[str]:
        """
        Notify idle workers about an available job.
        
        This method should use the workers:idle Redis set to find all idle workers
        and notify them about an available job. It should not perform any heartbeat
        checks or worker health monitoring, as those concerns should be handled by
        separate background processes.
        
        Args:
            job_id: Unique identifier for the job
            job_type: Type of job to be processed
            job_request_payload: Optional payload from the original job request as a JSON string
            
        Returns:
            List[str]: List of worker IDs that were notified
        """
        pass
