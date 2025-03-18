# EmProps Redis Hub

Redis Hub service for the EmProps Redis system.

## Overview

The Hub is the central component of the EmProps Redis system. It manages job distribution, worker communication, and real-time updates.

## Features

- WebSocket server for worker and client connections
- Redis pub/sub integration for real-time messaging
- Job queue management
- Worker status tracking
- Stale job cleanup

## Configuration

Configuration options are available in the `config/` directory.

## Running

To run the Hub service:

```bash
python main.py
```

## Development

The Hub service uses the core modules for its functionality. When making changes, ensure compatibility with the worker and API components.
