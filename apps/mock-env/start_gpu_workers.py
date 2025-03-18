#!/usr/bin/env python3
"""
GPU Worker Launcher
This script detects the number of available GPUs and launches the appropriate number of worker processes.
Each worker is assigned to a specific GPU using CUDA_VISIBLE_DEVICES.
"""

import os
import sys
import time
import subprocess
import multiprocessing
from typing import List, Dict

# Try to import nvidia-smi for GPU detection
try:
    import pynvml
    HAS_NVIDIA = True
except ImportError:
    HAS_NVIDIA = False
    print("WARNING: pynvml not found. GPU detection disabled.")

def get_gpu_count() -> int:
    """Detect the number of available GPUs"""
    if not HAS_NVIDIA:
        # Fallback to environment variable or default
        return int(os.environ.get("NUM_GPUS", 1))
    
    try:
        pynvml.nvmlInit()
        gpu_count = pynvml.nvmlDeviceGetCount()
        pynvml.nvmlShutdown()
        return gpu_count
    except Exception as e:
        print(f"Error detecting GPUs: {e}")
        # Fallback to environment variable or default
        return int(os.environ.get("NUM_GPUS", 1))

def start_worker(worker_id: str, gpu_id: int = None):
    """Start a worker process with the specified worker ID and GPU assignment"""
    env = os.environ.copy()
    env["WORKER_ID"] = worker_id
    
    # Assign specific GPU if available
    if gpu_id is not None:
        env["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
        print(f"Starting worker {worker_id} on GPU {gpu_id}")
    else:
        print(f"Starting worker {worker_id} without specific GPU assignment")
    
    # Start the worker process
    process = subprocess.Popen(
        [sys.executable, "main.py"],
        env=env,
        cwd="/app"
    )
    return process

def main():
    """Main function to start workers based on GPU count"""
    # Get the machine ID from environment or generate a default
    machine_id = os.environ.get("MACHINE_ID", "gpu-machine")
    
    # Detect number of GPUs
    gpu_count = get_gpu_count()
    print(f"Detected {gpu_count} GPUs")
    
    # Start one worker per GPU
    processes = []
    for gpu_id in range(gpu_count):
        worker_id = f"{machine_id}-gpu{gpu_id}"
        process = start_worker(worker_id, gpu_id)
        processes.append(process)
    
    # If no GPUs detected, start a single CPU worker
    if gpu_count == 0:
        worker_id = f"{machine_id}-cpu"
        process = start_worker(worker_id)
        processes.append(process)
    
    # Monitor worker processes and restart if needed
    try:
        while True:
            for i, process in enumerate(processes):
                if process.poll() is not None:
                    # Process has terminated, restart it
                    gpu_id = i if i < gpu_count else None
                    worker_id = f"{machine_id}-gpu{gpu_id}" if gpu_id is not None else f"{machine_id}-cpu"
                    print(f"Worker {worker_id} terminated, restarting...")
                    processes[i] = start_worker(worker_id, gpu_id)
            
            time.sleep(5)
    except KeyboardInterrupt:
        print("Shutting down workers...")
        for process in processes:
            process.terminate()
        
        # Wait for processes to terminate
        for process in processes:
            process.wait()

if __name__ == "__main__":
    main()
