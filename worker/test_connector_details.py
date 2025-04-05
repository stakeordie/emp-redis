#!/usr/bin/env python3
# Test script for connector details in progress updates
import os
import sys
import json
import asyncio
import websockets
from typing import Dict, Any, Optional

# Add the parent directory to the Python path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

# Add the worker directory to the Python path
worker_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, worker_dir)

# Import required modules
from connectors.comfyui_connector import ComfyUIConnector
from core.message_models import UpdateJobProgressMessage
from core.utils.logger import logger

async def test_connector_details():
    """Test connector details in progress updates"""
    
    # Initialize connector
    connector = ComfyUIConnector()
    await connector.initialize()
    
    # Mock websocket for testing
    class MockWebSocket:
        async def send(self, message):
            message_obj = json.loads(message)
            print(f"Message sent: {json.dumps(message_obj, indent=2)}")
    
    mock_ws = MockWebSocket()
    
    # Mock job ID
    job_id = "test-job-123"
    
    # Set up a mock progress update function
    async def send_progress_update(job_id, progress, status, message):
        # Get connector details
        connector_details = connector.get_connection_status()
        
        # Create progress update message
        progress_message = UpdateJobProgressMessage(
            job_id=job_id,
            worker_id="test-worker",
            progress=progress,
            status=status,
            message=message,
            connector_details=connector_details
        )
        
        # Send the progress update
        await mock_ws.send(progress_message.model_dump_json())
    
    # Test normal progress update
    print("\n=== Testing normal progress update ===")
    await send_progress_update(job_id, 50, "processing", "Processing test job")
    
    # Test heartbeat progress update
    print("\n=== Testing heartbeat progress update ===")
    await send_progress_update(job_id, -1, "heartbeat", "Heartbeat")
    
    # Set current job ID to simulate active job
    connector.current_job_id = job_id
    
    # Test progress update with active job
    print("\n=== Testing progress update with active job ===")
    await send_progress_update(job_id, 75, "processing", "Processing test job with active job")

if __name__ == "__main__":
    asyncio.run(test_connector_details())
