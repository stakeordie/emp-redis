#!/usr/bin/env python3
# 2025-04-25-19:12 - Test script for job reassignment logic

import os
import sys
import time
import uuid
import logging
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test_job_reassignment")

# Add the current directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import our Redis service
from core.redis_service import RedisService

def test_job_reassignment():
    """
    Test the job reassignment logic to ensure last_failed_worker is preserved.
    """
    # Create a Redis service instance
    redis_service = RedisService()
    
    # Generate a unique job ID for testing
    job_id = f"test-job-{uuid.uuid4()}"
    job_type = "test_job"
    worker_id = "test-worker-1"
    
    logger.info(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ STARTING JOB REASSIGNMENT TEST                                              ║
║ Job ID: {job_id}                                                             ║
║ Worker ID: {worker_id}                                                       ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
    
    # Step 1: Create a job
    logger.info("Step 1: Creating test job...")
    job_request_payload = {
        "max_retries": 3,
        "retry_count": 0,
        "params": {"test": "data"}
    }
    
    # Add the job with the correct method signature
    redis_service.add_job(job_id, job_type, 1, job_request_payload)
    
    # Step 2: Claim the job with our test worker
    logger.info(f"Step 2: Claiming job with worker {worker_id}...")
    claimed_job = redis_service.claim_job(job_id, worker_id)
    
    # Verify the job was claimed successfully
    if claimed_job is None:
        logger.error(f"Failed to claim job {job_id} with worker {worker_id}")
        return
        
    # Step 2.5: Verify worker_id is set correctly in Redis
    job_key = f"job:{job_id}"
    stored_worker_id = redis_service.client.hget(job_key, "worker_id")
    stored_worker = redis_service.client.hget(job_key, "worker")
    
    # Convert bytes to string if needed
    if isinstance(stored_worker_id, bytes):
        stored_worker_id = stored_worker_id.decode('utf-8')
    if isinstance(stored_worker, bytes):
        stored_worker = stored_worker.decode('utf-8')
    
    logger.info(f"Stored worker_id: {stored_worker_id}")
    logger.info(f"Stored worker: {stored_worker}")
    
    # Verify both fields are set correctly
    if stored_worker_id != worker_id or stored_worker != worker_id:
        logger.error(f"Worker ID mismatch! Expected: {worker_id}, Got worker_id: {stored_worker_id}, worker: {stored_worker}")
        return
    
    logger.info(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ JOB CLAIMED SUCCESSFULLY                                                   ║
║ Job ID: {job_id}                                                             ║
║ Worker ID: {worker_id}                                                       ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
    
    # Step 3: Mark the job as failed
    logger.info(f"Step 3: Marking job as failed by worker {worker_id}...")
    redis_service.fail_job(job_id, "Test failure")
    
    # Step 4: Verify last_failed_worker is set correctly
    logger.info("Step 4: Verifying last_failed_worker is set correctly...")
    job_key = f"job:{job_id}"
    last_failed_worker = redis_service.client.hget(job_key, "last_failed_worker")
    
    # Convert bytes to string if needed
    if isinstance(last_failed_worker, bytes):
        last_failed_worker = last_failed_worker.decode('utf-8')
    
    logger.info(f"Worker ID: {worker_id}")
    logger.info(f"Last Failed Worker: {last_failed_worker}")
    
    # Verify last_failed_worker is set correctly
    if last_failed_worker != worker_id:
        logger.error(f"last_failed_worker mismatch! Expected: {worker_id}, Got: {last_failed_worker}")
        return
        
    logger.info(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ LAST_FAILED_WORKER SET CORRECTLY                                           ║
║ Job ID: {job_id}                                                             ║
║ Worker ID: {worker_id}                                                       ║
║ Last Failed Worker: {last_failed_worker}                                     ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
    
    logger.info(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ VERIFICATION AFTER FAILURE                                                  ║
║ Job ID: {job_id}                                                             ║
║ Expected last_failed_worker: {worker_id}                                     ║
║ Actual last_failed_worker: {last_failed_worker}                              ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
    
    assert last_failed_worker == worker_id, f"Expected last_failed_worker to be {worker_id}, got {last_failed_worker}"
    
    # Step 5: Verify job status is now pending (requeued)
    logger.info("Step 5: Verifying job is requeued...")
    status = redis_service.client.hget(job_key, "status")
    
    if isinstance(status, bytes):
        status = status.decode('utf-8')
    
    logger.info(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ VERIFICATION AFTER REQUEUING                                                ║
║ Job ID: {job_id}                                                             ║
║ Expected status: pending                                                     ║
║ Actual status: {status}                                                      ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
    
    assert status == "pending", f"Expected status to be 'pending', got {status}"
    
    # Step 6: Attempt to claim the job with the same worker
    logger.info(f"Step 6: Attempting to claim job with same worker {worker_id}...")
    claimed_job = redis_service.claim_job(job_id, worker_id)
    
    logger.info(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ VERIFICATION OF CLAIM PREVENTION                                            ║
║ Job ID: {job_id}                                                             ║
║ Worker ID: {worker_id}                                                       ║
║ Claim result: {"PREVENTED" if claimed_job is None else "ALLOWED"}            ║
╚══════════════════════════════════════════════════════════════════════════════╝""")
    
    assert claimed_job is None, "Worker that previously failed the job should not be able to claim it"
    
    # Step 7: Clean up
    logger.info("Step 7: Cleaning up test job...")
    redis_service.client.delete(job_key)
    
    logger.info(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ TEST COMPLETED SUCCESSFULLY                                                 ║
║ All assertions passed                                                        ║
╚══════════════════════════════════════════════════════════════════════════════╝""")

if __name__ == "__main__":
    test_job_reassignment()
