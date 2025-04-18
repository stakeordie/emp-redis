#!/usr/bin/env python3
# Core Redis service for the queue system
import os
import json
import time
import datetime
import uuid
import redis
import redis.asyncio as aioredis
from typing import Dict, Any, Optional, List, Union, Callable, Set, Tuple
from pathlib import Path
from .utils.logger import logger
from .interfaces import RedisServiceInterface

# Import dotenv with type ignore for missing stubs
from dotenv import load_dotenv

# Redis configuration
# Using Redis URL as the standard connection method
# Format: redis://[[username]:[password]@][host][:port][/database]

# Get current working directory for debugging
cwd = os.getcwd()
logger.info(f"Current working directory: {cwd}")

# Check if .env files exist in various locations
root_env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
hub_env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'hub', '.env')
worker_env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'worker', '.env')
current_env = os.path.join(cwd, '.env')

logger.info(f"Root .env exists: {os.path.exists(root_env)}")
logger.info(f"Hub .env exists: {os.path.exists(hub_env)}")
logger.info(f"Worker .env exists: {os.path.exists(worker_env)}")
logger.info(f"Current dir .env exists: {os.path.exists(current_env)}")

# Try to load from all possible locations, with current directory having highest priority
if os.path.exists(root_env):
    logger.info(f"Loading root .env from: {root_env}")
    load_dotenv(root_env)

if os.path.exists(hub_env):
    logger.info(f"Loading hub .env from: {hub_env}")
    load_dotenv(hub_env)

if os.path.exists(worker_env):
    logger.info(f"Loading worker .env from: {worker_env}")
    load_dotenv(worker_env)

# Load from current directory with highest priority
if os.path.exists(current_env):
    logger.info(f"Loading current dir .env from: {current_env}")
    load_dotenv(current_env)

# Check environment variables before and after setting default
env_redis_url = os.environ.get("REDIS_URL")
logger.info(f"Environment REDIS_URL: {env_redis_url}")

# Set with default if needed
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
logger.info(f"Final REDIS_URL with default: {REDIS_URL}")

# Never hardcode URLs - always use environment variables
# If REDIS_URL is set in the environment, it will override the .env file

# Log Redis connection details with a distinctive marker
logger.info("*" * 50)
logger.info(f"****** REDIS CONNECTION URL: {REDIS_URL} ******")
logger.info("*" * 50)

# Redis host configuration

# Queue names
STANDARD_QUEUE = "job_queue"
PRIORITY_QUEUE = "priority_queue"
PENDING_JOBS_KEY = "jobs:pending"

# Redis key prefixes
JOB_PREFIX = "job:"
WORKER_PREFIX = "worker:"

class RedisService(RedisServiceInterface):
    """Core service for interacting with Redis for job queue operations
    
    Implements the RedisServiceInterface to ensure consistent API across the application.
    """
    

    
    def __init__(self):
        """Initialize Redis connections"""
        # Synchronous client for most operations
        logger.info("!" * 50)
        logger.info(f"!!! CONNECTING TO REDIS: {REDIS_URL} !!!")
        logger.info("!" * 50)
        self.client = redis.from_url(REDIS_URL, decode_responses=True)
        
        # Asynchronous client for pub/sub
        self.async_client = None
        self.pubsub = None
        
        # Reference to ConnectionManager (will be set after initialization)
        self.connection_manager = None
        
    def set_connection_manager(self, connection_manager):
        """Set the reference to ConnectionManager
        
        Args:
            connection_manager: The ConnectionManager instance to use
        """
        self.connection_manager = connection_manager

    async def connect_async(self) -> None:
        """
        Connect to Redis asynchronously for pub/sub operations.
        
        This method establishes an asynchronous connection to Redis
        for operations that require pub/sub functionality.
        """
        if self.async_client is None:
            logger.info("@" * 50)
            logger.info(f"@@@ CONNECTING ASYNC TO REDIS: {REDIS_URL} @@@")
            logger.info("@" * 50)
            self.async_client = aioredis.from_url(REDIS_URL, decode_responses=True)
            self.pubsub = self.async_client.pubsub()

    async def close_async(self) -> None:
        """
        Close the async Redis connection.
        
        This method properly closes the asynchronous Redis connection
        and cleans up any resources.
        """
        if self.pubsub:
            await self.pubsub.close()
        if self.async_client:
            await self.async_client.close()

    async def init_redis(self) -> bool:
        """
        Initialize Redis connections and data structures.
        
        This method ensures that both synchronous and asynchronous
        Redis connections are properly established and initializes
        any necessary data structures for the job queue system.
        
        Returns:
            bool: True if initialization was successful, False otherwise
        """
        # Ensure async connection is established
        await self.connect_async()
        
        # Initialize Redis data structures if they don't exist
        # Clear any stale temporary keys
        self.client.delete("temp:workers")
        
        # Create worker set if it doesn't exist
        if not self.client.exists("workers:all"):
            self.client.sadd("workers:all", "placeholder")  # Create the set
            self.client.srem("workers:all", "placeholder")  # Remove placeholder
            
        # Create idle workers set if it doesn't exist
        if not self.client.exists("workers:idle"):
            self.client.sadd("workers:idle", "placeholder")  # Create the set
            self.client.srem("workers:idle", "placeholder")  # Remove placeholder
            
        # Ensure queue structures exist
        if not self.client.exists(STANDARD_QUEUE):
            # Initialize empty list for standard queue
            self.client.rpush(STANDARD_QUEUE, "placeholder")  # Create the list
            self.client.lpop(STANDARD_QUEUE)  # Remove placeholder
            
        # Initialize job statistics counters if they don't exist
        stats_keys = ["stats:jobs:completed", "stats:jobs:failed", "stats:jobs:total"]
        for key in stats_keys:
            if not self.client.exists(key):
                self.client.set(key, 0)
                

        return True
    
    async def close(self) -> None:
        """
        Close all Redis connections.
        
        This method ensures that both synchronous and asynchronous
        Redis connections are properly closed and resources are released.
        """
        # Close async connections
        await self.close_async()
        
        # Close synchronous connection
        if self.client:
            self.client.close()

    # Job operations
    def add_job(self, job_id: str, job_type: str, priority: int, job_request_payload: Union[Dict[str, Any], str], client_id: Optional[str] = None) -> Dict[str, Any]:
        """Add a job to the queue
        
        Args:
            job_id: Unique identifier for the job
            job_type: Type of job to be processed
            priority: Job priority (higher values have higher priority)
            job_request_payload: The payload/configuration from the client's job request (either a dict or JSON string)
            client_id: Optional client identifier
            
        Returns:
            Dict[str, Any]: Job data including position in queue
        """
        job_key = f"{JOB_PREFIX}{job_id}"
        
        # 2025-04-09 14:14: Always generate a unique job ID when a collision is detected
        if self.client.exists(job_key):
            # Job with this ID already exists, log the issue
            logger.warning(f"[redis_service.py add_job()] Job ID collision detected: {job_id}. Generating new unique ID.")
            
            # Generate a new unique ID by appending a UUID
            new_job_id = f"{job_id}-{uuid.uuid4()}"
            logger.info(f"[redis_service.py add_job()] Generated new job_id: {new_job_id} to avoid collision")
            job_id = new_job_id
            job_key = f"{JOB_PREFIX}{job_id}"
            
            # Log that we're creating a new job with the unique ID
            logger.info(f"[redis_service.py add_job()] Creating new job with unique ID: {job_id}")
        
        # Ensure job_request_payload is a JSON string
        if isinstance(job_request_payload, dict):
            job_request_payload_json = json.dumps(job_request_payload)
        else:
            # Already a string, validate it's proper JSON
            try:
                # Parse and re-serialize to ensure it's valid JSON
                json.loads(job_request_payload)
                job_request_payload_json = job_request_payload
            except json.JSONDecodeError:
                # If not valid JSON, treat as a string and serialize it
                job_request_payload_json = json.dumps({"raw_payload": job_request_payload})
        
        # Store job details
        job_data = {
            "id": job_id,
            "job_type": job_type,  # Changed from 'type' to 'job_type' for consistency
            "priority": priority,
            "job_request_payload": job_request_payload_json,
            "status": "pending",
            "created_at": str(time.time()),
        }
        
        if client_id:
            job_data["client_id"] = client_id
            
        # 2025-04-09 13:39: Use Redis transaction to ensure atomicity
        pipe = self.client.pipeline()
        # Check again if the job exists (for extra safety)
        pipe.exists(job_key)
        pipe.hset(job_key, mapping=job_data)
        results = pipe.execute()
        logger.debug(f"[redis_service.py add_job()] Job added with ID: {job_data['id']}")
        
        # If the job already existed (first result is 1), log it
        if results[0] == 1:
            logger.warning(f"[redis_service.py add_job()] Race condition detected: job {job_id} was created between our checks")
        
        # Explicitly convert to string first, then to float
        created_at_str = str(job_data["created_at"])
        created_at = float(created_at_str)
        
        # Add 1 to priority to ensure all jobs use the priority queue
        adjusted_priority = priority + 1

        # Use a composite score that combines priority and creation timestamp
        # Higher priority jobs have higher scores
        # Within same priority, older jobs have higher scores (FIFO)
        composite_score = (adjusted_priority * 10000000000) - created_at

        self.client.zadd(PRIORITY_QUEUE, {job_id: composite_score})
        
        # Get queue position
        # Use zrevrank instead of zrank since we're using descending order
        # This gives us the position in the queue (0-indexed)
        position = self.client.zrevrank(PRIORITY_QUEUE, job_id)
        

        
        # Notify idle workers about the new job
        self.notify_idle_workers_of_job(job_id, job_type, job_request_payload=job_request_payload_json)
        

        
        # Return job data with position
        return job_data
    
    def update_job_progress(self, job_id: str, progress: int, message: Optional[str] = None) -> bool:
        """Update the progress of a job.
        
        Args:
            job_id: ID of the job to update
            progress: Progress percentage (0-100)
            message: Optional status message
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        # Get the worker_id from the job data
        job_key = f"{JOB_PREFIX}{job_id}"
        worker_id = self.client.hget(job_key, "worker_id")
        job_key = f"{JOB_PREFIX}{job_id}"
        
        # Check if job exists
        if not self.client.exists(job_key):

            return False
        
        # Update job progress
        self.client.hset(job_key, "progress", progress)
        if message:
            self.client.hset(job_key, "message", message)
        

        
        # Publish progress update event
        self.publish_job_update(job_id, "processing", progress=progress, message=message, worker_id=worker_id)
        
        return True
    
    def complete_job(self, job_id: str, result: Optional[Dict[str, Any]] = None) -> bool:
        """Mark a job as completed.
        
        Args:
            job_id: ID of the job to complete
            result: Optional job result data
            
        Returns:
            bool: True if completion was successful, False otherwise
        """
        # Get the worker_id from the job data
        job_key = f"{JOB_PREFIX}{job_id}"
        worker_id = self.client.hget(job_key, "worker_id")
        job_key = f"{JOB_PREFIX}{job_id}"
        
        # Check if job exists
        if not self.client.exists(job_key):

            return False
        
        # Update job status
        completed_at = time.time()
        self.client.hset(job_key, "status", "completed")
        self.client.hset(job_key, "completed_at", completed_at)
        
        # Add result if provided
        if result:
            self.client.hset(job_key, "result", json.dumps(result))
        
        logger.debug(f"[redis_service.py complete_job()] Job completed: {job_id}")

        # Publish completion event
        self.publish_job_update(job_id, "completed", result=result, worker_id=worker_id)
        
        return True
        
    def fail_job(self, job_id: str, error: str, max_retries: int = 4) -> bool:
        """Mark a job as failed and requeue it for processing if retry limit not exceeded.
        
        Args:
            job_id: ID of the job that failed
            error: Error message
            max_retries: Maximum number of retries before marking job as permanently failed
            
        Returns:
            bool: True if failure was recorded successfully, False otherwise
        """
        # 2025-04-17-15:47 - Added retry counter and max retry limit
        import time
        current_time = time.time()
        
        # Get the job data
        job_key = f"{JOB_PREFIX}{job_id}"
        
        # Check if job exists
        if not self.client.exists(job_key):
            logger.warning(f"[redis_service.py fail_job()]: Job {job_id} not found, cannot mark as failed")
            return False
        
        # Get job details
        worker_id = self.client.hget(job_key, "worker_id")
        job_type = self.client.hget(job_key, "job_type")
        priority_str = self.client.hget(job_key, "priority")
        retry_count_str = self.client.hget(job_key, "retry_count")
        
        # Get current retry count or initialize to 0
        try:
            retry_count = int(retry_count_str) if retry_count_str else 0
        except (ValueError, TypeError):
            retry_count = 0
            
        # Increment retry count
        retry_count += 1
        self.client.hset(job_key, "retry_count", retry_count)
        
        try:
            # Convert priority to integer if it exists
            priority = int(priority_str) if priority_str else 5  # Default priority
        except (ValueError, TypeError):
            priority = 5  # Default priority if conversion fails
            
        logger.info(f"[redis_service.py fail_job()]: Marking job {job_id} as failed with error: {error} (retry {retry_count}/{max_retries})")
        
        # Record the failure details
        self.client.hset(job_key, "last_error", error if error else "Unknown error")
        self.client.hset(job_key, "failed_at", str(current_time))
        
        # Clear worker assignment
        self.client.hdel(job_key, "worker_id")
        
        # Check if we've exceeded the retry limit
        if retry_count > max_retries:
            # Mark job as permanently failed
            self.client.hset(job_key, "status", "failed")
            self.client.hset(job_key, "permanent_failure", "true")
            self.client.hset(job_key, "failure_reason", f"Exceeded maximum retry limit of {max_retries}. Last error: {error}")
            
            logger.warning(f"[redis_service.py fail_job()]: Job {job_id} permanently failed after {retry_count} retries. Last error: {error}")
            
            # Publish permanent failure event
            self.publish_job_update(job_id, "failed", error=f"Exceeded maximum retry limit of {max_retries}. Last error: {error}", worker_id=worker_id, permanent=True)
            
            return True
        
        # If we haven't exceeded the retry limit, requeue the job
        # Update job status to pending so it can be processed again
        self.client.hset(job_key, "status", "pending")
        
        # Calculate composite score for priority queue (same logic as in add_job)
        created_at_str = self.client.hget(job_key, "created_at") or str(current_time)
        created_at = float(created_at_str)
        adjusted_priority = priority + 1
        composite_score = (adjusted_priority * 10000000000) - created_at
        
        # Add job back to the priority queue
        self.client.zadd(PRIORITY_QUEUE, {job_id: composite_score})
        
        logger.info(f"[redis_service.py fail_job()]: Job {job_id} requeued with priority {priority} (retry {retry_count}/{max_retries})")
        
        # Publish failure event
        self.publish_job_update(job_id, "failed", error=error, worker_id=worker_id, retry_count=retry_count, max_retries=max_retries)
        
        return True
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        logger.info(f"[INFO] Getting job status for {job_id}")
        """Get the current status of a job
        
        Args:
            job_id: ID of the job to check
            
        Returns:
            Optional[Dict[str, Any]]: Job status data if job exists, None otherwise
        """
        job_key = f"{JOB_PREFIX}{job_id}"
        
        # Check if job exists
        if not self.client.exists(job_key):
            return None
        
        # Get job details from Redis
        redis_result = self.client.hgetall(job_key)
        
        # Create a new dictionary with the Redis result to ensure proper typing
        job_data: Dict[str, Any] = dict(redis_result)
        
        # Parse job_request_payload and result if present
        if "job_request_payload" in job_data:
            try:
                job_data["job_request_payload"] = json.loads(job_data["job_request_payload"])
            except:
                job_data["job_request_payload"] = {}
        # For backward compatibility, also check for the old "params" key
        elif "params" in job_data:
            try:
                job_data["job_request_payload"] = json.loads(job_data["params"])
                # Remove the old key to avoid confusion
                del job_data["params"]
            except:
                job_data["job_request_payload"] = {}
                
        if "result" in job_data:
            try:
                job_data["result"] = json.loads(job_data["result"])
            except:
                job_data["result"] = {}
        
        # Add queue position if job is pending
        if job_data.get("status") == "pending":
            position: int = -1  # Default position if not found
            
            # Get position from priority queue using zrevrank
            # zrevrank can return None if the element is not in the sorted set

            rank_result = self.client.zrevrank(PRIORITY_QUEUE, job_id)
            
            if rank_result is not None:
                position = int(rank_result)
            
            # Add position to job data with explicit type
            job_data["position"] = position
        
        return job_data
    
    def register_worker(self, worker_id: str, capabilities: Optional[Dict[str, Any]] = None) -> bool:
        """Register a worker in Redis with detailed state information
        
        NOTE: Worker information is transitioning to be stored in-memory in ConnectionManager.
        This method is maintained for backwards compatibility but Redis operations are disabled.
        
        Args:
            worker_id: Unique identifier for the worker
            capabilities: Optional worker capabilities including supported job types
            
        Returns:
            bool: True if registration was successful, False otherwise
        """
        # TRANSITION: Worker information is now stored in-memory in ConnectionManager
        # Keeping this method for backwards compatibility
        return True
        
        # Original Redis implementation commented out
        """
        try:
            if worker_id.startswith("worker"):
                worker_key = f"{WORKER_PREFIX}{worker_id}"
            else:
                worker_key = f"{WORKER_PREFIX}worker{worker_id}"
                
            worker_info = capabilities or {}
            
            for key, value in list(worker_info.items()):
                if isinstance(value, bool):
                    worker_info[key] = str(value)
                elif isinstance(value, (int, float)):
                    worker_info[key] = str(value)
            
            current_time = time.time()
            worker_info["registered_at"] = current_time
            worker_info["last_heartbeat"] = current_time
            worker_info["status"] = "idle"
            worker_info["current_job_id"] = ""
            worker_info["jobs_processed"] = worker_info.get("jobs_processed", 0)
            worker_info["last_job_completed_at"] = worker_info.get("last_job_completed_at", 0)
            worker_info["updated_at"] = current_time
            
            if "supported_job_types" in worker_info:
                if isinstance(worker_info["supported_job_types"], list):
                    worker_info["supported_job_types"] = json.dumps(worker_info["supported_job_types"])
                elif not isinstance(worker_info["supported_job_types"], str):
                    worker_info["supported_job_types"] = str(worker_info["supported_job_types"])
            
            self.client.hset(worker_key, mapping=worker_info)
            self.client.expire(worker_key, 86400)
            self.client.sadd("workers:all", worker_id)
            self.client.sadd("workers:idle", worker_id)
            return True
        except Exception as e:
            logger.error(f"Error registering worker {worker_id}: {str(e)}")
            return False
        """

    def worker_heartbeat(self, worker_id: str) -> bool:
        """
        Record a heartbeat from a worker (in-memory only, no longer uses Redis).
        
        Args:
            worker_id: ID of the worker sending the heartbeat
            
        Returns:
            bool: True if heartbeat was recorded successfully, False otherwise
        """
        # This is now a no-op since worker heartbeats are tracked in memory by ConnectionManager
        # We always return True to maintain compatibility with existing code
        # logger.debug(f"Worker heartbeat recorded for {worker_id} (in-memory only)")
        return True
        
    def update_worker_heartbeat(self, worker_id: str, status: Optional[str] = None, 
                                  additional_data: Optional[Dict[str, Any]] = None) -> bool:
        """Update worker heartbeat timestamp (in-memory only, no longer uses Redis)
        
        Args:
            worker_id: ID of the worker to update
            status: Optional new status (e.g., "idle", "busy")
            additional_data: Optional additional worker state data to update
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        # This is now a no-op since worker heartbeats are tracked in memory by ConnectionManager
        # We always return True to maintain compatibility with existing code
        # logger.debug(f"Worker heartbeat received for {worker_id} (in-memory only)")
        
        # If status is provided, log it for debugging purposes
        # if status is not None:
        #     logger.debug(f"Worker {worker_id} status updated to {status} (in-memory only)")
            
        return True
        
    def worker_exists(self, worker_id: str) -> bool:
        """Check if a worker exists (in-memory only, no longer uses Redis)"""
        # This is now a no-op that always returns True
        # The actual worker existence check is handled by ConnectionManager
        # logger.debug(f"Worker existence check for {worker_id} (in-memory only)")
        return True
    
    def update_worker_status(self, worker_id: str, status: str, job_id: Optional[str] = None, 
                                additional_data: Optional[Dict[str, Any]] = None) -> bool:
        """Update the status and state information of a worker (in-memory only, no longer uses Redis).
        
        Args:
            worker_id: ID of the worker to update
            status: New status (e.g., "idle", "busy", "disconnected")
            job_id: Optional ID of the job the worker is processing
            additional_data: Optional additional worker state data to update
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        # This is now a no-op since worker status is tracked in memory by ConnectionManager
        # We always return True to maintain compatibility with existing code
        # logger.debug(f"Worker status update for {worker_id} to {status} (in-memory only)")
        
        # If job_id is provided, log it for debugging purposes
        # if job_id is not None:
        #     logger.debug(f"Worker {worker_id} assigned to job {job_id} (in-memory only)")
            
        return True
        
    def update_worker_capabilities(self, worker_id: str, capabilities: Dict[str, Any]) -> bool:
        """Update worker capabilities"""
        worker_key = f"{WORKER_PREFIX}{worker_id}"
        
        # Check if worker exists
        if not self.client.exists(worker_key):
            return False
        
        # Convert capabilities dict to JSON string
        capabilities_json = json.dumps(capabilities)
        
        # Update worker capabilities
        self.client.hset(worker_key, "capabilities", capabilities_json)
        
        # Refresh TTL for worker key (24 hours)
        self.client.expire(worker_key, 86400)  # 24 hours in seconds
        
        return True
        
    def reassign_worker_jobs(self, worker_id: str) -> int:
        """
        Reassign jobs from a disconnected worker back to the pending queue.
        
        Args:
            worker_id: Worker ID to reassign jobs from
            
        Returns:
            Number of jobs reassigned
        """
        try:
            # Initialize counter for reassigned jobs
            reassigned_count = 0
            
            # Find any jobs assigned to this worker
            job_keys = self.client.keys(f"{JOB_PREFIX}*")
            
            for job_key in job_keys:
                job_key_str = job_key  # Already a string with decode_responses=True
                job_id = job_key_str.replace(f"{JOB_PREFIX}", "")
                
                # Get job worker and status
                job_worker = self.client.hget(job_key, "worker")
                job_status = self.client.hget(job_key, "status")
                
                # With decode_responses=True, these will already be strings
                # No need for byte conversion checks
                
                # Only reset jobs that are in processing status and assigned to this worker
                if job_worker == worker_id and job_status == "processing":
                    # Get job priority
                    priority_bytes = self.client.hget(job_key, "priority")
                    priority = int(priority_bytes) if priority_bytes else 0
                    
                    # Reset job status to pending
                    self.client.hset(job_key, "status", "pending")
                    self.client.hdel(job_key, "worker")
                    
                    # Add back to pending queue with original priority
                    self.client.zadd(PENDING_JOBS_KEY, {job_id: priority})
                    
                    # Add a note about reassignment
                    current_time = time.time()
                    note = f"Job reassigned at {current_time:.0f} due to worker disconnect"
                    self.client.hset(job_key, "reassigned_at", current_time)
                    self.client.hset(job_key, "reassignment_note", note)
                    
                    # Increment counter
                    reassigned_count += 1
                    
                    # logger.info(f"Reassigned job {job_id} from disconnected worker {worker_id}")
            
            return reassigned_count
            
        except Exception as e:
            logger.error(f"Error reassigning worker jobs: {str(e)}")
            return 0
            
    def mark_stale_workers(self, max_heartbeat_age: int = 60) -> None:
        """Mark workers as disconnected if they haven't sent a heartbeat recently
        
        NOTE: Worker heartbeat tracking is transitioning to be stored in-memory in ConnectionManager.
        This method is maintained for backwards compatibility but Redis operations are disabled.
        
        Args:
            max_heartbeat_age: Maximum age in seconds before a worker is considered stale
        """
        # TRANSITION: Worker heartbeats are now tracked in-memory by ConnectionManager
        # This function is kept for backwards compatibility but is now a no-op
        pass
        
        # Original Redis implementation commented out
        """
        try:
            current_time = time.time()
            
            # Get all worker keys
            worker_keys = self.client.keys(f"{WORKER_PREFIX}*")
            
            for worker_key in worker_keys:
                # Get worker ID from key
                worker_id = worker_key.replace(WORKER_PREFIX, "")
                
                # Get worker status and last heartbeat
                worker_status_bytes = self.client.hget(worker_key, "status")
                last_heartbeat_bytes = self.client.hget(worker_key, "last_heartbeat")
                
                if not worker_status_bytes or not last_heartbeat_bytes:
                    continue
                    
                worker_status = worker_status_bytes
                last_heartbeat = float(last_heartbeat_bytes) if last_heartbeat_bytes else 0
                
                heartbeat_age = current_time - last_heartbeat
                
                if worker_status == "disconnected":
                    continue
                    
                if heartbeat_age > max_heartbeat_age:
                    self.update_worker_status(worker_id, "disconnected")
                    self.reassign_worker_jobs(worker_id)
                    
        except Exception as e:
            logger.error(f"Error marking stale workers: {str(e)}")
        """

    def get_worker_info(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a worker
        
        NOTE: Worker information is transitioning to be stored in-memory in ConnectionManager.
        This method is maintained for backwards compatibility but Redis operations are disabled.
        
        Args:
            worker_id: ID of the worker to get information about
            
        Returns:
            Optional[Dict[str, Any]]: Worker information if worker exists, None otherwise
        """
        # TRANSITION: Worker information is now stored in-memory in ConnectionManager
        # This function should be updated to fetch from ConnectionManager instead
        return None
        
        # Original Redis implementation commented out
        """
        worker_key = f"{WORKER_PREFIX}{worker_id}"
        
        # Get all worker info from hash
        worker_info = self.client.hgetall(worker_key)
        
        if not worker_info:
            return None
            
        return worker_info
        """
    
    def request_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get system statistics
        
        Returns:
            Dict[str, Any]: Dictionary containing statistics about queues, jobs, and workers
        """
        # Initialize stats structure with explicit type annotations
        stats: Dict[str, Dict[str, Any]] = {
            "queues": {
                "priority": 0,
                "standard": 0,
                "total": 0
            },
            "jobs": {
                "total": 0,
                "status": {},
                "active_jobs": []
            },
            "workers": {
                "total": 0,
                "status": {},
                "active_workers": []
            }
        }
        
        try:
            # Queue stats - ensure proper type conversion from Redis return values
            # All jobs now use the priority queue
            priority_count: int = int(self.client.zcard(PRIORITY_QUEUE))
            
            # Keep standard_count for backward compatibility, but it should always be 0
            standard_count: int = 0
            
            stats["queues"]["priority"] = priority_count
            stats["queues"]["standard"] = standard_count
            stats["queues"]["total"] = priority_count  # Total is just priority count now
            
            # Job stats
            job_keys = self.client.keys(f"{JOB_PREFIX}*")
            stats["jobs"]["total"] = len(job_keys)
            
            # Job status counts and detailed job information
            for job_key in job_keys:
                # Extract job ID from Redis key
                job_id = job_key.replace(JOB_PREFIX, "")  # Already a string with decode_responses=True
                
                # Get all job data
                job_data = self.client.hgetall(job_key)
                
                if job_data:
                    # Update job status counts
                    job_status = job_data.get("status", "unknown")
                    current_count = stats["jobs"]["status"].get(job_status, 0)
                    stats["jobs"]["status"][job_status] = current_count + 1
                    
                    # Add detailed information for active jobs (pending, active, failed)
                    if job_status in ["pending", "active", "failed"]:
                        # Add detailed job information with priority field
                        job_info = {
                            "id": job_id,
                            "job_type": job_data.get("job_type", job_data.get("type", "")),
                            "status": job_status,
                            "priority": int(job_data.get("priority", 0)),
                            "worker_id": job_data.get("worker", None),
                            "created_at": float(job_data.get("created_at", 0)),
                            "updated_at": float(job_data.get("updated_at", 0)),
                            "progress": int(job_data.get("progress", 0)) if "progress" in job_data else None
                        }
                        stats["jobs"]["active_jobs"].append(job_info)
            
            # Worker stats from ConnectionManager
            # Get all worker info from ConnectionManager
            worker_info = self.connection_manager.worker_info
            stats["workers"]["total"] = len(worker_info)
            
            # Worker status counts and detailed worker information
            for worker_id, info in worker_info.items():
                # Update worker status counts
                worker_status = info.get("status", "unknown")
                current_count = stats["workers"]["status"].get(worker_status, 0)
                stats["workers"]["status"][worker_status] = current_count + 1
                
                # Add detailed worker information
                worker_detail = {
                    "id": worker_id,
                    "status": worker_status,
                    "connected_at": info.get("registered_at", 0),
                    "jobs_processed": info.get("jobs_processed", 0),
                    "last_heartbeat": info.get("last_heartbeat", 0),
                    "current_job_id": info.get("current_job_id", "")
                }
                stats["workers"]["active_workers"].append(worker_detail)
            
        except Exception as e:
            # Keep the empty stats structure in case of errors
            print(f"Error in request_stats: {str(e)}")
        
        return stats
        
    def notify_idle_workers_of_job(self, job_id: str, job_type: str, job_request_payload: Optional[str] = None) -> List[str]:
        # Parameter is now correctly typed as Optional[str] to match interface
        """
        Notify idle workers about an available job.
        
        This method uses the workers:idle Redis set to find all idle workers
        and notify them about an available job. It does not perform any heartbeat
        checks or worker health monitoring, as those concerns are handled by
        separate background processes.
        
        Args:
            job_id: Unique identifier for the job
            job_type: Type of job to be processed
            job_request_payload: Optional payload from the original job request as a JSON string
            
        Returns:
            List[str]: List of worker IDs that were notified
        """
        # Get all idle workers directly from the Redis set
        idle_workers = self.client.smembers("workers:idle")
        
        # Log the number of idle workers found
        logger.info(f"[JOB-NOTIFY] Found {len(idle_workers)} idle workers for job {job_id} (type: {job_type})")
        if idle_workers:
            logger.debug(f"[JOB-NOTIFY] Idle workers: {list(idle_workers)}")
        
        # Publish notification to job channel
        notification = {
            "type": "job_available",
            "job_id": job_id,
            "job_type": job_type
        }
        
        if job_request_payload:
            # Include the original job request payload in the notification
            notification["job_request_payload"] = job_request_payload
        
        # Log before publishing
        logger.info(f"[JOB-NOTIFY] Publishing job notification for job {job_id} (type: {job_type}) to channel job_notifications")
        
        # Publish and get the number of clients that received the message
        publish_result = self.client.publish("job_notifications", json.dumps(notification))
        
        # Log the number of clients that received the message
        logger.info(f"[JOB-NOTIFY] Job notification for job {job_id} was received by {publish_result} subscribers")
        
        return list(idle_workers)
    
    def claim_job(self, job_id: str, worker_id: str, claim_timeout: int = 30) -> Optional[Dict[str, Any]]:
        """Atomically claim a job with a timeout"""
        job_key = f"{JOB_PREFIX}{job_id}"
        
        # Use Redis transaction to ensure atomicity
        with self.client.pipeline() as pipe:
            try:
                # Watch the job status to ensure it's still pending
                pipe.watch(job_key)
                job_status = pipe.hget(job_key, "status")
                
                if job_status != "pending":
                    pipe.unwatch()

                    return None
                
                # Start transaction
                pipe.multi()
                
                # Update job status to claimed with timeout
                pipe.hset(job_key, "status", "claimed")
                pipe.hset(job_key, "worker", worker_id)
                pipe.hset(job_key, "claimed_at", time.time())
                pipe.hset(job_key, "claim_timeout", claim_timeout)
                
                # Execute transaction
                pipe.execute()
                
                # Get job details from Redis and convert to proper dictionary
                redis_result = self.client.hgetall(job_key)
                job_data: Dict[str, Any] = dict(redis_result)
                
                # Parse params back to dict
                if "params" in job_data:
                    # Convert the JSON string to a dictionary
                    params_str = job_data["params"]
                    if isinstance(params_str, str):
                        job_data["params"] = json.loads(params_str)
                

                return job_data
                
            except Exception as e:

                return None
    
    def get_pending_jobs_by_type(self, job_type: str) -> List[Dict[str, Any]]:
        """
        Get all pending jobs of a specific type from Redis, sorted by priority and age.
        
        This method searches through the priority queue for pending jobs of the specified type.
        Jobs are returned sorted by priority (highest first) and then by age (oldest first).
        
        Args:
            job_type: The type of job to search for
            
        Returns:
            List[Dict[str, Any]]: List of job data dictionaries for pending jobs of the specified type
        """
        try:
            result_jobs = []
            
            # Get all jobs from priority queue
            priority_jobs = self.client.zrange(PRIORITY_QUEUE, 0, -1, withscores=True, desc=True)
            # logger.info(f"[JOB-MATCH] Found {len(priority_jobs)} total jobs in priority queue")
            
            # Check each job to see if it's pending and of the right type
            for job_id, composite_score in priority_jobs:
                job_id_str = job_id  # Already a string with decode_responses=True
                # logger.info(f"[JOB-MATCH] Checking job {job_id_str} in priority queue")
                job_key = f"{JOB_PREFIX}{job_id_str}"
                
                # logger.debug(f"[JOB-MATCH] Checking job {job_id_str} in priority queue")
                # Check if job exists, is pending, and is of the right type
                pipe = self.client.pipeline()
                pipe.hget(job_key, "status")
                pipe.hget(job_key, "job_type")
                status, current_job_type = pipe.execute()
                
                # logger.debug(f"[JOB-MATCH] Job {job_id_str} status: {status}, type: {current_job_type}, job_type: {job_type}, job_type[0]: {job_type[0]}")
                
                if status == "pending" and current_job_type == job_type: #AI HELP NEEDS FIXING
                    # Get all job data
                    # logger.debug(f"[{job_type} CAPABLE WORKERS FOUND] Job {job_id_str} is pending and of type {job_type}")
                    job_data = self.client.hgetall(job_key)
                    if job_data:
                        job_dict: Dict[str, Any] = job_data
                        job_dict["id"] = job_id_str  # Add the job ID to the dict
                        result_jobs.append(job_dict)
            
            # if result_jobs:
            #     logger.info(f"[JOB-MATCH] Found {len(result_jobs)} pending jobs of type {job_type}")
            # else:
            #     logger.info(f"[JOB-MATCH] No pending jobs found of type {job_type}")
                
            return result_jobs
            
        except Exception as e:
            logger.error(f"[JOB-MATCH] Error in get_pending_jobs_by_type: {str(e)}")
            return []
    
    def get_next_pending_job(self) -> Optional[Dict[str, Any]]:
        """Get the next highest priority pending job from Redis
        
        This method checks both the priority queue and standard queue for pending jobs,
        prioritizing jobs from the priority queue. It returns the job data for the
        highest priority pending job.
        
        Returns:
            Optional[Dict[str, Any]]: Job data dictionary or None if no pending jobs
        """
        try:
            # Check priority queue for pending jobs
            # logger.info("[DEBUG] Checking priority queue for pending jobs")
            
            # Get jobs from priority queue, already sorted by composite score (highest first)
            # This ensures higher priority jobs come first, and within same priority, older jobs come first
            priority_jobs = self.client.zrange(PRIORITY_QUEUE, 0, -1, withscores=True, desc=True)
            # logger.info(f"[DEBUG] Found {len(priority_jobs)} jobs in priority queue: {priority_jobs}")
            
            # No need to sort again since Redis returns them in the right order
            # Just use the jobs in the order they come from Redis
            sorted_priority_jobs = priority_jobs
            # logger.info(f"[DEBUG] Processing priority jobs in order: {sorted_priority_jobs}")
            
            for job_id, composite_score in sorted_priority_jobs:
                job_id_str = job_id  # Already a string with decode_responses=True
                # logger.info(f"[DEBUG] Checking job: {job_id_str} with composite score {composite_score}")
                job_key = f"{JOB_PREFIX}{job_id_str}"
                
                # Check if job exists and is pending
                job_status = self.client.hget(job_key, "status")
                if job_status:
                    # logger.info(f"[DEBUG] Job {job_id_str} status: {job_status}")
                    
                    if job_status == "pending":
                        # logger.info(f"[DEBUG] Found pending job: {job_id_str}")
                        # Get all job data
                        job_data = self.client.hgetall(job_key)
                        if job_data:
                            # With decode_responses=True, all keys and values are already strings
                            job_dict: Dict[str, Any] = job_data
                            job_dict["id"] = job_id_str  # Add the job ID to the dict
                            # logger.info(f"[DEBUG] Returning job data: {job_dict}")
                            return job_dict
                        else:
                            logger.info(f"[DEBUG] No job data found for {job_id_str}")
                else:
                    logger.info(f"[DEBUG] No status found for job {job_id_str}")
            
            # No pending jobs found
            # logger.info("[DEBUG] No pending jobs found in priority queue")
            return None
            
        except Exception as e:
            logger.error(f"[DEBUG] Error in get_next_pending_job: {str(e)}")
            return None
    
    def cleanup_stale_claims(self, max_claim_age: int = 60) -> int:
        """Reset jobs that were claimed but never started processing"""
        current_time = time.time()
        stale_count = 0
        
        # Find claimed jobs
        job_keys = self.client.keys(f"{JOB_PREFIX}*")
        
        for job_key in job_keys:
            job_id = job_key.replace(f"{JOB_PREFIX}", "")
            job_status = self.client.hget(job_key, "status")
            
            # Only check claimed jobs
            if job_status == "claimed":
                claimed_at = float(self.client.hget(job_key, "claimed_at") or 0)
                claim_age = current_time - claimed_at
                claim_timeout = int(self.client.hget(job_key, "claim_timeout") or 30)
                
                # Check if claim is stale
                if claim_age > claim_timeout:
                    # Get job priority
                    priority = int(self.client.hget(job_key, "priority") or 0)
                    
                    # Reset job status to pending
                    self.client.hset(job_key, "status", "pending")
                    self.client.hdel(job_key, "worker")
                    self.client.hdel(job_key, "claimed_at")
                    self.client.hdel(job_key, "claim_timeout")
                    
                    # Add back to queue
                    if priority > 0:
                        self.client.zadd(PRIORITY_QUEUE, {job_id: priority})
                    else:
                        self.client.lpush(STANDARD_QUEUE, job_id)
                        

                    stale_count += 1
        
        return stale_count
    
    # Redis pub/sub methods
    def publish_job_update(self, job_id: str, status: str, **kwargs) -> bool:
        """Publish a job update event"""
        try:
            # Create update message
            message = {
                "job_id": job_id,
                "status": status,
                "timestamp": time.time(),
                **kwargs
            }
            
            # Publish to job-specific channel
            self.client.publish(f"job_updates:{job_id}", json.dumps(message))
            
            # Also publish to global job updates channel
            self.client.publish("job_updates", json.dumps(message))
            
            return True
        except Exception as e:

            return False
    
    async def subscribe_to_channel(self, channel: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Subscribe to a Redis channel for updates"""
        if not self.async_client:
            await self.connect_async()
        
        # Ensure pubsub is not None before attempting to subscribe
        if self.pubsub:
            await self.pubsub.subscribe(**{channel: callback})

        
    def get_all_workers_status(self) -> Dict[str, Dict[str, Any]]:
        """Get detailed status information for all workers
        
        Returns:
            Dictionary with worker IDs as keys and worker status information as values
        """
        workers_status = {}
        current_time = time.time()
        
        try:
            # Get all worker keys
            worker_keys = self.client.keys(f"{WORKER_PREFIX}*")
            
            for worker_key in worker_keys:
                worker_id = worker_key.replace(f"{WORKER_PREFIX}", "")
                # Get worker details from Redis and convert to proper dictionary
                redis_result = self.client.hgetall(worker_key)
                
                # Convert bytes to strings for all values
                worker_data: Dict[str, Any] = {}
                for key, value in redis_result.items():
                    key_str = key  # Already a string with decode_responses=True
                    value_str = value  # Already a string with decode_responses=True
                    worker_data[key_str] = value_str
                
                # Convert numeric fields to appropriate types
                for field in ["registered_at", "last_heartbeat", "updated_at", "last_job_completed_at"]:
                    if field in worker_data and worker_data[field]:
                        try:
                            worker_data[field] = float(worker_data[field])
                        except (ValueError, TypeError):
                            pass
                
                if "jobs_processed" in worker_data and worker_data["jobs_processed"]:
                    try:
                        worker_data["jobs_processed"] = int(worker_data["jobs_processed"])
                    except (ValueError, TypeError):
                        pass
                
                # Parse JSON fields
                if "supported_job_types" in worker_data and worker_data["supported_job_types"]:
                    try:
                        worker_data["supported_job_types"] = json.loads(worker_data["supported_job_types"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                        
                # Parse capabilities if present
                if "capabilities" in worker_data and worker_data["capabilities"]:
                    try:
                        worker_data["capabilities"] = json.loads(worker_data["capabilities"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                
                # Add additional calculated fields
                if "last_heartbeat" in worker_data:
                    last_heartbeat = float(worker_data["last_heartbeat"]) if isinstance(worker_data["last_heartbeat"], str) else worker_data["last_heartbeat"]
                    worker_data["heartbeat_age"] = current_time - last_heartbeat
                    
                    # Add a human-readable last_seen field
                    last_seen_time = datetime.datetime.fromtimestamp(last_heartbeat)
                    worker_data["last_seen"] = last_seen_time.strftime("%Y-%m-%d %H:%M:%S")
                
                # Add uptime if registered_at is available
                if "registered_at" in worker_data:
                    registered_at = float(worker_data["registered_at"]) if isinstance(worker_data["registered_at"], str) else worker_data["registered_at"]
                    worker_data["uptime_seconds"] = current_time - registered_at
                    
                    # Add a human-readable uptime field
                    uptime_seconds = int(worker_data["uptime_seconds"])
                    hours, remainder = divmod(uptime_seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    worker_data["uptime"] = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
                
                # Add to result dictionary
                workers_status[worker_id] = worker_data
            
        except Exception as e:
            logger.error(f"Error getting worker status: {str(e)}")
            
        return workers_status

        
    def get_jobs_by_status_type_priority(
        self, 
        status: str = None, 
        job_type: str = None, 
        min_priority: int = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve jobs filtered by status, type, and minimum priority
        
        Args:
            status (str, optional): Job status to filter by
            job_type (str, optional): Job type to filter by
            min_priority (int, optional): Minimum priority to filter by
        
        Returns:
            List[Dict[str, Any]]: Filtered and sorted list of jobs
        """
        try:
            # Find all job keys
            job_keys = self.client.keys(f'{JOB_PREFIX}*')
            
            # Filter jobs
            matching_jobs = []
            for key in job_keys:
                job_data = self.client.hgetall(key)
                
                # Apply filters
                if (status is None or job_data.get('status') == status) and \
                (job_type is None or job_data.get('job_type') == job_type) and \
                (min_priority is None or 
                    int(job_data.get('priority', 0)) >= min_priority):
                    
                    # Add job ID and convert creation time
                    job_data['job_id'] = key.replace(JOB_PREFIX, '')
                    job_data['created_at'] = float(job_data.get('created_at', 0))
                    job_data['priority'] = int(job_data.get('priority', 0))
                    
                    matching_jobs.append(job_data)
            
            # Sort jobs by priority (descending) and then by creation date (ascending)
            sorted_jobs = sorted(
                matching_jobs, 
                key=lambda x: (-x['priority'], x['created_at'])
            )
            
            # Add position numbers
            for position, job in enumerate(sorted_jobs, 1):
                job['position'] = position
            
            return sorted_jobs
        
        except Exception as e:
            logger.error(f"[DEBUG] Error in get_jobs_by_status_type_priority: {str(e)}")
            return []