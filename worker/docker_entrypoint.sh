#!/bin/bash
# Docker entrypoint script for the worker

# Print current directory
echo "Current directory: $(pwd)"

# Fix imports
echo "Fixing imports..."
python fix_imports.py

# Run the worker
echo "Starting worker..."
python main.py
