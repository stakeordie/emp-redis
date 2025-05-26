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

# Check if .env files exist in various locations
root_env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
hub_env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'hub', '.env')
worker_env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'worker', '.env')
current_env = os.path.join(cwd, '.env')

# Try to load from all possible locations, with current directory having highest priority
if os.path.exists(root_env):
    load_dotenv(root_env)

if os.path.exists(hub_env):
    load_dotenv(hub_env)

if os.path.exists(worker_env):
    load_dotenv(worker_env)

# Load from current directory with highest priority
if os.path.exists(current_env):
    load_dotenv(current_env)

# Check environment variables before and after setting default
env_redis_url = os.environ.get("REDIS_URL")

# Set with default if needed
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Never hardcode URLs - always use environment variables
# If REDIS_URL is set in the environment, it will override the .env file

# Redis host configuration

# Queue names
STANDARD_QUEUE = "job_queue"
PRIORITY_QUEUE = "priority_queue"
PENDING_JOBS_KEY = "jobs:pending"

# Redis key prefixes
JOB_PREFIX = "job:"
WORKER_PREFIX = "worker:"
CLIENT_PREFIX = "client:"
PRIORITY_QUEUE = "job_priority_queue"
JOB_CHANNEL = "job_notifications"
WORKER_CHANNEL = "worker_notifications"
CLIENT_CHANNEL = "client_notifications"

# 2025-04-25-19:15 - Default values for job processing
DEFAULT_MAX_RETRIES = 3
DEFAULT_JOB_PRIORITY = 1

class RedisService(RedisServiceInterface):
    """Core service for interacting with Redis for job queue operations
    
    Implements the RedisServiceInterface to ensure consistent API across the application.
    """
    

    
    def __init__(self):
        """Initialize Redis connections"""
        # Synchronous client for most operations
        self.client = redis.from_url(REDIS_URL, decode_responses=True)
        
        # Asynchronous client for pub/sub
        self.async_client = None
        self.pubsub = None
        
        # Reference to ConnectionManager (will be set after initialization)
        self.connection_manager = None
        
        # [2025-05-23T08:45:00-04:00] - Clean up any stale worker records during initialization
        # This ensures we start with a clean state and prevents WebSocket message size issues
        try:
            # We need to delay this cleanup until after __init__ completes
            # It will be called from set_connection_manager instead
            pass
        except Exception as e:
            logger.error(f"[2025-05-23T08:45:00-04:00] Error during initialization cleanup: {str(e)}")
            # Non-fatal error, continue initialization
        
    def set_connection_manager(self, connection_manager):
        """Set the reference to ConnectionManager
        
        Args:
            connection_manager: The ConnectionManager instance to use
        """
        self.connection_manager = connection_manager
        
        # [2025-05-23T08:46:00-04:00] - Clean up any stale worker records now that connection_manager is set
        try:
            # Now that we have the connection manager, we can safely clean up stale worker records
            worker_count = len(self.client.keys(f"{WORKER_PREFIX}*"))
            if worker_count > 0:
                self.cleanup_stale_worker_records()
        except Exception as e:
            logger.error(f"[2025-05-23T08:46:00-04:00] Error during stale worker cleanup: {str(e)}")
            # Non-fatal error, continue initialization

    async def connect_async(self) -> None:
        """
        Connect to Redis asynchronously for pub/sub operations.
        
        This method establishes an asynchronous connection to Redis
        for operations that require pub/sub functionality.
        """
        if self.async_client is None:
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
        # [2025-05-26T00:30:00-04:00] Add detailed debug logging for job type tracking
        logger.debug(f"[2025-05-26T00:30:00-04:00] [redis_service.py] Adding job {job_id} with job_type: '{job_type}'")
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
            logger.error(f"[redis_service.py add_job()] Job ID collision detected: {job_id}. Generating new unique ID.")
            
            # Generate a new unique ID by appending a UUID
            new_job_id = f"{job_id}-{uuid.uuid4()}"
            # Generated a new job_id to avoid collision
            job_id = new_job_id
            job_key = f"{JOB_PREFIX}{job_id}"
            
            # Log that we're creating a new job with the unique ID
            # Creating new job with unique ID
        
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
        
        # [2025-05-26T00:30:00-04:00] Log job data for debugging
        logger.debug(f"[2025-05-26T00:30:00-04:00] [redis_service.py] Job data for {job_id}: job_type='{job_type}', priority={priority}, status='pending'")
        
        if client_id:
            job_data["client_id"] = client_id
            
        # 2025-04-09 13:39: Use Redis transaction to ensure atomicity
        pipe = self.client.pipeline()
        # Check again if the job exists (for extra safety)
        pipe.exists(job_key)
        pipe.hset(job_key, mapping=job_data)
        results = pipe.execute()        
        # If the job already existed (first result is 1), log it
        if results[0] == 1:
            logger.error(f"[redis_service.py add_job()] Race condition detected: job {job_id} was created between our checks")
        
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
        logger.debug(f"[2025-05-26T00:30:00-04:00] [redis_service.py] Notifying idle workers about new job {job_id} of type '{job_type}'")
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
        
        # Update last_updated_at timestamp to reset timeout clock
        current_time = time.time()
        self.client.hset(job_key, "last_updated_at", current_time)        
        # [2025-05-20T21:27:00-04:00] Don't publish progress update events
        # This eliminates duplicate messages since the original message is already being forwarded
        # The original message contains more information (connector_details) than what we would publish here
        # self.publish_job_update(job_id, "processing", progress=progress, message=message, worker_id=worker_id)
        
        return True
    
    def complete_job(self, job_id: str, result: Optional[Dict[str, Any]] = None) -> bool:
        """Mark a job as completed.
        
        Args:
            job_id: ID of the job to complete
            result: Optional job result data
            
        Returns:
            bool: True if completion was successful, False otherwise
        """
        # [2025-05-20T18:29:00-04:00] Enhanced logging for job completion
        if result:
            result_keys = list(result.keys()) if isinstance(result, dict) else "not a dict"
        
        # Get the worker_id from the job data
        job_key = f"{JOB_PREFIX}{job_id}"
        worker_id = self.client.hget(job_key, "worker_id")
        
        # Check if job exists
        if not self.client.exists(job_key):
            logger.error(f"[2025-05-20T18:29:00-04:00] Job {job_id} not found in Redis, cannot complete")
            return False
        
        # Update job status
        completed_at = time.time()
        self.client.hset(job_key, "status", "completed")
        self.client.hset(job_key, "completed_at", completed_at)
        
        # Add result if provided
        if result:
            # [2025-05-20T18:29:00-04:00] Ensure result is properly serialized
            try:
                result_json = json.dumps(result)
                self.client.hset(job_key, "result", result_json)                
                # Verify the result was stored correctly
                stored_result = self.client.hget(job_key, "result")
            except Exception as e:
                logger.error(f"[2025-05-20T18:29:00-04:00] Error storing result for job {job_id}: {str(e)}")
        else:
            logger.error(f"[2025-05-20T18:29:00-04:00] No result provided for job {job_id}")
                
        # [2025-05-23T08:55:26-04:00] Ensure we return a boolean value as declared in the function signature
        # Previously this was set to True unconditionally, but we should reflect the actual storage success
        storage_success = stored_result is not None
        
        # [2025-05-20T21:28:00-04:00] Don't publish job updates
        # This eliminates duplicate messages since the original message is already being forwarded
        # The original message contains more information (connector_details) than what we would publish here
        # if stored_result:
        #     self.publish_job_update(job_id, "completed", result=result, worker_id=worker_id)
        
        return storage_success
        
    def cancel_job(self, job_id: str, reason: str = "Manually cancelled") -> bool:
        """Permanently cancel a job and remove it from the queue.
        
        This method:
        1. Removes the job from the priority queue (if present)
        2. Updates the job status to "cancelled" in Redis
        3. Adds a cancellation timestamp and reason
        4. Notifies any subscribed clients about the cancellation
        
        Args:
            job_id: ID of the job to cancel
            reason: Reason for cancellation (default: "Manually cancelled")
            
        Returns:
            bool: True if cancellation was successful, False otherwise
        """
        # 2025-04-26-21:30 - Added method to permanently cancel jobs
        import time
        current_time = time.time()
        
        # Get the job data
        job_key = f"{JOB_PREFIX}{job_id}"
        
        # Check if job exists
        if not self.client.exists(job_key):
            logger.error(f"[redis_service.py cancel_job()]: Job {job_id} not found, cannot cancel")
            return False
            
        worker_id = self.client.hget(job_key, "worker_id")

        # Update job with cancellation information
        update_fields = {
            "status": "cancelled",
            "cancelled_at": current_time,
            "cancellation_reason": reason,
            "message": f"Job cancelled: {reason}"
        }
        
        self.client.hset(job_key, mapping=update_fields)
        
        # Publish cancellation event
        self.publish_job_update(job_id, "cancelled", reason=reason, worker_id=worker_id)
        
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
        # 2025-04-25-15:30 - Added tracking of failed workers to ensure job alternates between workers
        import time
        current_time = time.time()
        
        # Get the job data
        job_key = f"{JOB_PREFIX}{job_id}"
        
        # Check if job exists
        if not self.client.exists(job_key):
            logger.error(f"[redis_service.py fail_job()]: Job {job_id} not found, cannot mark as failed")
            return False
        
        # Get job details
        worker_id = self.client.hget(job_key, "worker_id")
        job_type = self.client.hget(job_key, "job_type")
        
        # 2025-04-25-19:14 - BUGFIX: Get retry_count from Redis before incrementing
        retry_count_str = self.client.hget(job_key, "retry_count")
        retry_count = int(retry_count_str) if retry_count_str else 0
        retry_count += 1
        
        # Convert bytes to string if needed
        if isinstance(worker_id, bytes):
            worker_id = worker_id.decode('utf-8')
        if isinstance(job_type, bytes):
            job_type = job_type.decode('utf-8')
        
        # Get max retries from job or use default
        max_retries = self.client.hget(job_key, "max_retries")
        max_retries = int(max_retries) if max_retries else DEFAULT_MAX_RETRIES
        
        # Log the failure with retry information
        logger.error(f"[redis_service.py fail_job()]: Marking job {job_id} as failed with error: {error} (retry {retry_count}/{max_retries})")
        
        # 2025-04-25-18:50 - Explicitly store the worker_id that failed this job
        # This is critical for preventing the same worker from being reassigned the job
        # 2025-04-25-19:17 - BUGFIX: Only set last_failed_worker if worker_id is not None
        if worker_id:
            self.client.hset(job_key, "last_failed_worker", worker_id)
            
            # Log the worker ID being stored
            logger.error(f"""[redis_service.py fail_job()]
╔══════════════════════════════════════════════════════════════════════════════╗
║ STORED LAST_FAILED_WORKER IN REDIS                                        ║
║ Job ID: {job_id}                                                             ║
║ Worker ID: {worker_id}                                                       ║
║ Redis Key: {job_key}                                                         ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
        else:
            logger.error(f"""[redis_service.py fail_job()]
╔══════════════════════════════════════════════════════════════════════════════╗
║ NO WORKER ID TO STORE AS LAST_FAILED_WORKER                               ║
║ Job ID: {job_id}                                                             ║
║ Redis Key: {job_key}                                                         ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
        
        # Worker ID logging is now handled in the conditional block above
        
        # Update job with failure information
        self.client.hset(job_key, "status", "failed")
        self.client.hset(job_key, "error", error)
        self.client.hset(job_key, "retry_count", retry_count)
        
        # Check if we've exceeded max retries
        if retry_count > max_retries:
            logger.error(f"[redis_service.py fail_job()]: Job {job_id} permanently failed after {retry_count} retries. Last error: {error}")
            return False
            
        # Requeue the job with the same priority
        priority = self.client.hget(job_key, "priority")
        priority = int(priority) if priority else DEFAULT_JOB_PRIORITY
        
        # If we haven't exceeded the retry limit, requeue the job
        # 2025-04-25-18:58 - CRITICAL FIX: Preserve last_failed_worker when requeuing
        # First, get the current last_failed_worker value to verify it's set
        current_last_failed_worker = self.client.hget(job_key, "last_failed_worker")
        if isinstance(current_last_failed_worker, bytes):
            current_last_failed_worker = current_last_failed_worker.decode('utf-8')
            
        # 2025-04-25-19:14 - BUGFIX: Remove duplicate code block
        # The current_last_failed_worker is already retrieved and decoded above
            
        # Create a dictionary with all the fields we want to update atomically
        update_fields = {
            "status": "pending",
        }
        
        # Ensure we're explicitly preserving the last_failed_worker field
        if current_last_failed_worker:
            update_fields["last_failed_worker"] = current_last_failed_worker
            
        # Update job status and preserve last_failed_worker in a single operation
        self.client.hmset(job_key, update_fields)
        
        # Verify last_failed_worker is still set after changing status
        post_status_last_failed_worker = self.client.hget(job_key, "last_failed_worker")
        if isinstance(post_status_last_failed_worker, bytes):
            post_status_last_failed_worker = post_status_last_failed_worker.decode('utf-8')
            
        # Calculate composite score for priority queue (same logic as in add_job)
        created_at_str = self.client.hget(job_key, "created_at") or str(current_time)
        created_at = float(created_at_str)
        adjusted_priority = priority + 1
        composite_score = (adjusted_priority * 10000000000) - created_at
        
        # Add job back to the priority queue
        self.client.zadd(PRIORITY_QUEUE, {job_id: composite_score})
        
        # Verify last_failed_worker is still set after adding to queue
        final_last_failed_worker = self.client.hget(job_key, "last_failed_worker")
        if isinstance(final_last_failed_worker, bytes):
            final_last_failed_worker = final_last_failed_worker.decode('utf-8')
            
        # Log the requeuing with last_failed_worker tracking
        logger.error(f"""[redis_service.py fail_job()]
╔══════════════════════════════════════════════════════════════════════════════╗
║ JOB REQUEUED WITH LAST_FAILED_WORKER TRACKING                               ║
║ Job ID: {job_id}                                                             ║
║ Priority: {priority}                                                         ║
║ Retry: {retry_count}/{max_retries}                                          ║
║ Initial last_failed_worker: {current_last_failed_worker}                     ║
║ After status change: {post_status_last_failed_worker}                        ║
║ Final last_failed_worker: {final_last_failed_worker}                         ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
        
        # Publish failure event
        self.publish_job_update(job_id, "failed", error=error, worker_id=worker_id, retry_count=retry_count, max_retries=max_retries)
        
        return True
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
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
        # Added: 2025-04-29T19:05:00-04:00 - Fixed linting issues with exception handling
        if "job_request_payload" in job_data:
            try:
                job_data["job_request_payload"] = json.loads(job_data["job_request_payload"])
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse job_request_payload for job {job_id}: {str(e)}")
                job_data["job_request_payload"] = {}
        # For backward compatibility, also check for the old "params" key
        elif "params" in job_data:
            try:
                job_data["job_request_payload"] = json.loads(job_data["params"])
                # Remove the old key to avoid confusion
                del job_data["params"]
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse params for job {job_id}: {str(e)}")
                job_data["job_request_payload"] = {}
        
        if "result" in job_data:
            try:
                job_data["result"] = json.loads(job_data["result"])
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse result for job {job_id}: {str(e)}")
                job_data["result"] = {}
        
        # Add queue position if job is pending
        if job_data.get("status") == "pending":
            # [2025-05-20T14:07:04-04:00] Fixed position calculation to only count pending jobs
            # We need to count only pending jobs that are ahead in the queue, not all jobs
            
            position: int = 0  # Default position if not found or first in queue
            
            # [2025-05-20T14:20:37-04:00] Fixed position calculation to consider both priority and creation time
            job_score = self.client.zscore(PRIORITY_QUEUE, job_id)
            job_created_at = float(job_data.get("created_at", 0))
            
            if job_score is not None:
                # Get all jobs from the priority queue in correct order
                # Use zrevrange to get jobs in order of highest priority (highest score) first
                all_jobs = self.client.zrevrange(PRIORITY_QUEUE, 0, -1)
                
                # Count pending jobs that should be processed before this one
                pending_jobs_ahead = 0
                
                # Keep track of all jobs for debugging
                job_details = []
                
                for other_job_id in all_jobs:
                    # Skip the current job
                    other_job_id_str = other_job_id.decode('utf-8') if isinstance(other_job_id, bytes) else other_job_id
                    if other_job_id_str == job_id:
                        continue
                    
                    # Get the status of this job
                    other_job_status = self.client.hget(f"job:{other_job_id_str}", "status")
                    if not other_job_status:
                        continue
                        
                    other_job_status_str = other_job_status.decode('utf-8') if isinstance(other_job_status, bytes) else other_job_status
                    
                    # Only count jobs that are still pending
                    if other_job_status_str == "pending":
                        # Get the score (priority) of this job
                        other_job_score = self.client.zscore(PRIORITY_QUEUE, other_job_id)
                        if other_job_score is None:
                            continue
                        
                        # Get the creation time of this job
                        # Use hgetall to get all fields for the job
                        other_job_data_raw = self.client.hgetall(f"job:{other_job_id_str}")
                        
                        # Convert bytes to strings in the job data
                        other_job_data = {}
                        for k, v in other_job_data_raw.items():
                            key = k.decode('utf-8') if isinstance(k, bytes) else k
                            value = v.decode('utf-8') if isinstance(v, bytes) else v
                            other_job_data[key] = value
                            
                        other_job_created_at = float(other_job_data.get("created_at", 0)) if other_job_data else 0
                        
                        # Build job details for debugging
                        job_detail = {
                            "job_id": other_job_id_str,
                            "score": other_job_score,
                            "created_at": other_job_created_at,
                            "status": other_job_status_str
                        }
                        job_details.append(job_detail)
                        
                        # [2025-05-20T15:34:23-04:00] Fixed job priority comparison
                        # For our composite score calculation: (priority * 10000000000) - created_at
                        # Higher scores have higher priority because we subtract the timestamp
                        # We need to check if the other job's score is HIGHER than this job's score
                        if other_job_score > job_score:
                            # This job has higher priority (higher score)
                            pending_jobs_ahead += 1
                        # For jobs with same priority, count those created earlier
                        elif other_job_score == job_score and other_job_created_at < job_created_at:
                            pending_jobs_ahead += 1
                
                # [2025-05-23T19:48:33-04:00] Reverted to 0-based indexing for job positions
                # This is the natural way to represent queue positions (0 = next up, 1 = one job ahead, etc.)
                position = pending_jobs_ahead
                
                # Log the queue order for easier debugging
                queue_order = []
                for job_detail in job_details:
                    if job_detail['status'] == 'pending':
                        queue_order.append(job_detail['job_id'])            
            # Add position to job data with explicit type
            job_data["position"] = position
        
        # [2025-05-26T00:25:00-04:00] Add retry_count as failures to the job status response
        if "retry_count" in job_data:
            try:
                # Convert retry_count to int and add as failures
                retry_count = int(job_data["retry_count"])
                job_data["failures"] = retry_count
                logger.debug(f"[2025-05-26T00:25:00-04:00] [redis_service.py] Added failure count {retry_count} to job status for job {job_id}")
            except (ValueError, TypeError) as e:
                logger.error(f"[2025-05-26T00:25:00-04:00] [redis_service.py] Error converting retry_count to int for job {job_id}: {str(e)}")
                job_data["failures"] = 0
        else:
            # If retry_count is not present, set failures to 0
            job_data["failures"] = 0
            
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
        return True
        
    def worker_exists(self, worker_id: str) -> bool:
        """Check if a worker exists (in-memory only, no longer uses Redis)"""
        # This is now a no-op that always returns True
        # The actual worker existence check is handled by ConnectionManager
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
            
        return True
        
    def update_worker_capabilities(self, worker_id: str, capabilities: Dict[str, Any]) -> bool:
        """Update worker capabilities (in-memory only, no longer uses Redis)
        
        Args:
            worker_id: ID of the worker to update
            capabilities: Dictionary of worker capabilities
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        # [2025-05-23T08:42:00-04:00] - Fixed inconsistency in worker tracking transition
        # This is now a no-op since worker capabilities are tracked in memory by ConnectionManager
        # We always return True to maintain compatibility with existing code
        # Worker capabilities update (in-memory only)
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
            # Added: 2025-04-29T19:05:00-04:00 - Fixed null check for connection_manager
            # Get all worker info from ConnectionManager if it exists
            if self.connection_manager is not None:
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
        
        # 2025-04-25-18:58 - Enhanced verification of last_failed_worker field
        job_key = f"{JOB_PREFIX}{job_id}"
        
        # Get all job fields to verify the job's current state
        job_fields = self.client.hgetall(job_key)
        job_retry_count = None
        
        if job_fields:
            # Convert all bytes values to strings
            job_fields = {k.decode('utf-8') if isinstance(k, bytes) else k: 
                         v.decode('utf-8') if isinstance(v, bytes) else v 
                         for k, v in job_fields.items()}
            
            # Extract key fields
            job_retry_count = job_fields.get('retry_count')
            
        
        # 2025-04-25-23:35 - Removed Redis-based worker filtering
        # We now use in-memory tracking in ConnectionManager to prevent reassigning failed jobs
        # This simplifies the Redis service and centralizes the worker status management
        
        # Convert all idle workers to strings (from bytes if needed)
        filtered_workers = set()
        for worker in idle_workers:
            # Convert bytes to string if needed
            worker_id = worker.decode('utf-8') if isinstance(worker, bytes) else worker
            filtered_workers.add(worker_id)
        
        # Get the last_failed_worker field for logging purposes only
        last_failed_worker = self.client.hget(job_key, "last_failed_worker")
        if last_failed_worker and isinstance(last_failed_worker, bytes):
            last_failed_worker = last_failed_worker.decode('utf-8')
        
        
        # 2025-04-25-23:40 - Removed duplicate logging and fixed excluded_count reference
        # The worker notification summary is now handled by the ConnectionManager
        
        # 2025-04-25-23:45 - Removed detailed worker information section
        # This information is now handled by the ConnectionManager
        # The Redis service no longer needs to track worker capabilities or exclusions
        # All worker filtering is now done in memory by the ConnectionManager
        
        # 2025-04-25-23:50 - Removed warning about all workers being excluded
        # This is now handled by the ConnectionManager
        
        # Publish notification to job channel
        # 2025-04-25-22:51 - Enhanced job notification with more details
        # This provides workers with more information about the job and makes last_failed_worker more prominent
        notification = {
            "type": "job_available",
            "job_id": job_id,
            "job_type": job_type,
            "timestamp": time.time(),
            "retry_count": job_retry_count,
            "priority": job_fields.get('priority') if job_fields else None,
        }
        
        # Explicitly add last_failed_worker to the notification if it exists
        if last_failed_worker:
            notification["last_failed_worker"] = last_failed_worker
            notification["excluded_worker"] = last_failed_worker  # More explicit field name
            
            # Add a warning message to the notification
            notification["warning"] = f"Worker {last_failed_worker} previously failed this job and should not claim it"
        
        if job_request_payload:
            # Include the original job request payload in the notification
            notification["job_request_payload"] = job_request_payload
        
        
        # Publish and get the number of clients that received the message        
        
        return list(filtered_workers)
    
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
                
                # Check if this worker was the last one to fail this job
                last_failed_worker = pipe.hget(job_key, "last_failed_worker")
                
                # 2025-04-25-18:10 - Fixed comparison by converting bytes to string
                # Redis returns bytes for hget operations, but worker_id is a string
                if last_failed_worker:
                    # Convert bytes to string if needed
                    if isinstance(last_failed_worker, bytes):
                        last_failed_worker = last_failed_worker.decode('utf-8')
                                        
                    # If this worker was the last one to fail this job, don't let it claim it again
                    if last_failed_worker == worker_id:
                        # 2025-04-25-22:51 - Enhanced logging for claim rejection                        
                        # Check if there are other idle workers that could claim this job                                                
                        pipe.unwatch()
                        return None
                
                # Start transaction
                pipe.multi()
                
                # Update job status to claimed with timeout
                pipe.hset(job_key, "status", "claimed")
                # 2025-04-25-19:22 - Changed from "worker" to "worker_id" for consistency
                # This ensures the worker_id field is properly set for the last_failed_worker logic
                pipe.hset(job_key, "worker_id", worker_id)
                # Keep the worker field for backward compatibility
                pipe.hset(job_key, "worker", worker_id)
                current_time = time.time()
                pipe.hset(job_key, "claimed_at", current_time)
                pipe.hset(job_key, "last_updated_at", current_time)  # Initialize last_updated_at to claimed_at
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
                logger.error(f"[redis_service.py claim_job()]: Error claiming job {job_id} for worker {worker_id}: {str(e)}")
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
            
            logger.debug(f"[2025-05-26T00:25:00-04:00] [redis_service.py] Searching for pending jobs of type: {job_type}")
            
            # Get all jobs from priority queue
            priority_jobs = self.client.zrange(PRIORITY_QUEUE, 0, -1, withscores=True, desc=True)
            logger.debug(f"[2025-05-26T00:25:00-04:00] [redis_service.py] Found {len(priority_jobs)} total jobs in priority queue")
            
            # Check each job to see if it's pending and of the right type
            for job_id, composite_score in priority_jobs:
                job_id_str = job_id  # Already a string with decode_responses=True
                job_key = f"{JOB_PREFIX}{job_id_str}"
                
                # Check if job exists, is pending, and is of the right type
                pipe = self.client.pipeline()
                pipe.hget(job_key, "status")
                pipe.hget(job_key, "job_type")
                status, current_job_type = pipe.execute()
                
                
                # Log job type comparison for debugging
                logger.debug(f"[2025-05-26T00:25:00-04:00] [redis_service.py] Job {job_id_str} - status: {status}, job_type: {current_job_type}, looking for type: {job_type}")
                
                if status == "pending" and current_job_type == job_type: #AI HELP NEEDS FIXING
                    # Get all job data
                    job_data = self.client.hgetall(job_key)
                    if job_data:
                        job_dict: Dict[str, Any] = job_data
                        job_dict["id"] = job_id_str  # Add the job ID to the dict
                        result_jobs.append(job_dict)
                        logger.debug(f"[2025-05-26T00:25:00-04:00] [redis_service.py] ✅ Matched job {job_id_str} of type {current_job_type}")
                else:
                    if status == "pending":
                        logger.debug(f"[2025-05-26T00:25:00-04:00] [redis_service.py] ❌ Job type mismatch: {current_job_type} ≠ {job_type} for job {job_id_str}")
                            
            logger.debug(f"[2025-05-26T00:25:00-04:00] [redis_service.py] Found {len(result_jobs)} pending jobs of type {job_type}")
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
            # Get jobs from priority queue, already sorted by composite score (highest first)
            # This ensures higher priority jobs come first, and within same priority, older jobs come first
            priority_jobs = self.client.zrange(PRIORITY_QUEUE, 0, -1, withscores=True, desc=True)
            
            # No need to sort again since Redis returns them in the right order
            # Just use the jobs in the order they come from Redis
            sorted_priority_jobs = priority_jobs
            
            for job_id, composite_score in sorted_priority_jobs:
                job_id_str = job_id  # Already a string with decode_responses=True
                job_key = f"{JOB_PREFIX}{job_id_str}"
                
                # Check if job exists and is pending
                job_status = self.client.hget(job_key, "status")
                if job_status:
                    
                    if job_status == "pending":
                        # Get all job data
                        job_data = self.client.hgetall(job_key)
                        if job_data:
                            # With decode_responses=True, all keys and values are already strings
                            job_dict: Dict[str, Any] = job_data
                            job_dict["id"] = job_id_str  # Add the job ID to the dict
                            return job_dict
                        else:
                            logger.error(f"[2025-05-25T14:55:00-04:00] No job data found for {job_id_str}")
                else:
                    logger.error(f"[2025-05-25T14:55:00-04:00] No status found for job {job_id_str}")
            
            # No pending jobs found
            return None
            
        except Exception as e:
            logger.error(f"[2025-05-25T14:55:00-04:00] Error in get_next_pending_job: {str(e)}")
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
                # Get the last_updated_at timestamp, falling back to claimed_at if not present
                last_updated_at = float(self.client.hget(job_key, "last_updated_at") or 
                                      self.client.hget(job_key, "claimed_at") or 0)
                inactive_time = current_time - last_updated_at
                claim_timeout = int(self.client.hget(job_key, "claim_timeout") or 30)
                remaining_time = claim_timeout - inactive_time
                
                # Add debug logging for timeout tracking
                job_id = job_key.replace(f"{JOB_PREFIX}", "")                
                # Check if job has been inactive for longer than the timeout
                if inactive_time > claim_timeout:
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

        
    def cleanup_stale_worker_records(self) -> bool:
        """Remove all worker records from Redis
        
        This method is used to clean up stale worker records that may have been created
        during the transition from Redis-based worker tracking to in-memory tracking.
        
        Returns:
            bool: True if cleanup was successful, False otherwise
        """
        # [2025-05-23T08:43:00-04:00] - Added method to clean up stale worker records
        try:
            # Find all worker keys
            worker_keys = self.client.keys(f"{WORKER_PREFIX}*")
            
            if worker_keys:
                # Delete all worker keys
                self.client.delete(*worker_keys)                
            # Also clean up worker sets
            self.client.delete("workers:all")
            self.client.delete("workers:idle")
            self.client.delete("workers:busy")
            
            return True
        except Exception as e:
            logger.error(f"[2025-05-23T08:43:00-04:00] Error cleaning up stale worker records: {str(e)}")
            return False
            
    def get_all_workers_status(self) -> Dict[str, Dict[str, Any]]:
        """Get detailed status information for all workers
        
        NOTE: Worker information is transitioning to be stored in-memory in ConnectionManager.
        This method will now return an empty dictionary to prevent large WebSocket messages
        with stale worker data. The actual worker status should be obtained from ConnectionManager.
        
        Returns:
            Dictionary with worker IDs as keys and worker status information as values
        """
        # [2025-05-23T08:43:00-04:00] - Updated to return empty dict during transition period
        # This prevents large WebSocket messages with stale worker data        
        # Clean up any stale worker records that might still exist in Redis
        self.cleanup_stale_worker_records()
        
        # Return empty dictionary - worker status should now come from ConnectionManager
        return {}

        
    def get_jobs_by_status_type_priority(
        self, 
        status: Optional[str] = None, 
        job_type: Optional[str] = None, 
        min_priority: Optional[int] = None
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
            logger.error(f"[2025-05-25T14:55:00-04:00] Error in get_jobs_by_status_type_priority: {str(e)}")
            return []