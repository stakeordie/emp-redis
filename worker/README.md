# EmProps Redis Worker

Worker service for the EmProps Redis system.

## Overview

The Worker component connects to the Redis Hub and processes jobs from the queue.

## Features

- WebSocket connection to the Hub
- Job processing and status reporting
- Heartbeat mechanism for worker status tracking
- Configurable worker capabilities

## Configuration

Configuration options are available in the `config/` directory.

## Running

To run the Worker service:

```bash
python main.py
```

## Development

The Worker service uses the core modules for its functionality. When making changes, ensure compatibility with the Hub service.
