#!/usr/bin/env python3
# Test script for connector details in progress updates for both connectors
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
from connectors.simulation_connector import SimulationConnector
from core.message_models import UpdateJobProgressMessage
from core.utils.logger import logger

async def test_connector_details():
    """Test connector details in progress updates for both connectors"""
    
    # Initialize connectors
    comfyui_connector = ComfyUIConnector()
    simulation_connector = SimulationConnector()
    
    await comfyui_connector.initialize()
    await simulation_connector.initialize()
    
    # Mock websocket for testing
    class MockWebSocket:
        async def send(self, message):
            message_obj = json.loads(message)
            print(f"Message sent: {json.dumps(message_obj, indent=2)}")
    
    mock_ws = MockWebSocket()
    
    # Mock job IDs
    comfyui_job_id = "comfyui-job-123"
    simulation_job_id = "simulation-job-456"
    
    # Set up mock progress update functions
    async def send_comfyui_progress(job_id, progress, status, message):
        # Get connector details
        connector_details = comfyui_connector.get_connection_status()
        
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
    
    async def send_simulation_progress(job_id, progress, status, message):
        # Get connector details
        connector_details = simulation_connector.get_connection_status()
        
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
    
    # Test ComfyUI connector
    print("\n=== Testing ComfyUI connector ===")
    comfyui_connector.current_job_id = comfyui_job_id
    version_message = f"Processing ComfyUI job [version: {comfyui_connector.VERSION}]"
    await send_comfyui_progress(comfyui_job_id, 50, "processing", version_message)
    
    # Test Simulation connector
    print("\n=== Testing Simulation connector ===")
    simulation_connector.current_job_id = simulation_job_id
    version_message = f"Processing Simulation job [version: {simulation_connector.VERSION}]"
    await send_simulation_progress(simulation_job_id, 50, "processing", version_message)
    
    # Test heartbeat progress updates
    print("\n=== Testing heartbeat progress updates ===")
    comfyui_heartbeat = f"ComfyUI Heartbeat [version: {comfyui_connector.VERSION}]"
    simulation_heartbeat = f"Simulation Heartbeat [version: {simulation_connector.VERSION}]"
    await send_comfyui_progress(comfyui_job_id, -1, "heartbeat", comfyui_heartbeat)
    await send_simulation_progress(simulation_job_id, -1, "heartbeat", simulation_heartbeat)

if __name__ == "__main__":
    asyncio.run(test_connector_details())
