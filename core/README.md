# EmProps Redis Core

Core modules for the EmProps Redis system.

## Overview

This directory contains the shared core modules used by the Hub, Worker, and API components. These modules provide the fundamental functionality for Redis communication, WebSocket handling, and data modeling.

## Modules

- **connections.py**: WebSocket connection management
- **models.py**: Data models and schemas
- **redis_service.py**: Redis interaction logic
- **routes.py**: Core route definitions

## Usage

These modules are imported and used by the other components in the system. They are not meant to be run directly.

## Development

When making changes to these core modules, be aware that they affect all components in the system.
