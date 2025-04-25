# Changelog

All notable changes to the EMP Redis project will be documented in this file.

## [Unreleased]

### Added
- [2025-04-25 15:30] Added smart job reassignment for failed jobs:
  - Failed jobs now alternate between available workers
  - Jobs will not be reassigned to the same worker that just failed them
  - Implemented by tracking the last worker that failed each job
  - Modified job claim logic to check and respect worker exclusion
- [2025-04-07 10:04] Added REST connectors for workers:
  - `rest_sync_connector.py` for synchronous REST API calls
  - `rest_async_connector.py` for asynchronous REST API calls with polling
- [2025-04-06 20:21] Enhanced Redis hub to send all job progress information to monitors, including client IDs
- [2025-04-06 20:21] Modified job completion notifications to also be sent to all monitors with client ID information

### Changed
- [2025-04-07 10:04] Moved `websocket_connector.py` to the connectors directory for better organization
- [2025-04-07 10:04] Updated import paths and log prefixes in connector files
- [2025-04-07 16:00] Added connection management to WebSocket-based connectors (ComfyUIConnector) to prevent connections from remaining open after job completion
- [2025-04-07 16:00] Added environment variable `WORKER_COMFYUI_KEEP_CONNECTION` to control WebSocket connection persistence

### Changed
- [2025-04-07 15:52] Added connector_name attribute to SimulationConnector for proper connector identification
- [2025-04-07 15:53] Simplified connector loading by removing complex dependency handling
- [2025-04-07 15:52] Updated WebSocketConnector to set connector_name to None to indicate it's not directly usable
- [2025-04-07 15:51] Implemented `connector_name` class attribute for explicit connector identification
- [2025-04-07 15:50] Updated connector_loader.py to use connector_name attribute for reliable connector class detection
- [2025-04-07 15:06] Implemented connector dependency handling in connector_loader.py to ensure proper loading order
- [2025-04-07 15:05] Fixed import issues in comfyui_connector.py to properly extend WebSocketConnector
- [2025-04-07 15:04] Updated import strategy in connectors to use proper package imports and handle multiple import scenarios
- [2025-04-07 14:59] Added worker_main.py as a new entry point outside the worker package to solve import issues
- [2025-04-07 14:58] Updated worker/__init__.py to properly expose BaseWorker and other components
- [2025-04-07 14:57] Updated GitHub workflow to include worker_main.py in the package
- [2025-04-07 14:56] Modified docker_entrypoint.sh to use worker_main.py as the primary entry point
- [2025-04-07 11:44] Updated worker.py and base_worker.py to use robust package imports through __init__.py files
- [2025-04-07 11:39] Added comprehensive diagnostics to connector_loader.py to help debug package structure issues
- [2025-04-07 11:34] Updated docker_entrypoint.sh to navigate to the correct directory in the new structure
- [2025-04-07 11:32] Updated Docker worker setup to match GitHub workflow package structure for consistent imports across environments

### Fixed
- [2025-04-07 11:20] Implemented a location-independent import system in `connector_loader.py` that works regardless of app location
- [2025-04-07 11:13] Enhanced `__init__.py` files with comprehensive module exports and proper package structure
- [2025-04-07 11:10] Enhanced `connector_loader.py` to try multiple import patterns for better Docker compatibility
- [2025-04-07 11:07] Improved package structure with proper `__init__.py` files to ensure imports work in all environments
- [2025-04-07 11:05] Simplified import statements in connector files to use a consistent approach
- [2025-04-07 10:54] Fixed import paths in `comfyui_connector.py` to properly reference the moved WebSocket connector
- [2025-04-07 10:54] Removed the old `websocket_connector.py` file from the worker directory to avoid confusion

## [0.1.1] - 2025-04-06

### Added
- [2025-04-06 21:00] Simple Redis Monitor: Added client ID column to job tables and enhanced connection handling

### Fixed
- [2025-04-06 21:00] Simple Redis Monitor: Fixed job type display in finished jobs table by properly capturing and preserving job type information in all job status handlers
- [2025-04-06 21:00] Simple Redis Monitor: Restored proper connection handling for both monitor and client connections

## [0.1.0] - 2025-04-06

### Added
- New "Finished Jobs" table that displays completed, failed, and cancelled jobs
- Absolute datetime formatting (YYYY-MM-DD HH:MM:SS) for job start and finish times
- Job cancellation handling with proper UI updates
- Placeholder for workers with no active jobs to prevent UI jumping
- This CHANGELOG.md file to track changes across development sessions

### Changed
- Removed redundant job tables from worker cards
- Made worker cards more compact with smaller fonts
- Fixed height containers to prevent UI jumping when content changes
- Improved progress bar styling and visibility
- Reorganized UI to separate active, queued, and finished jobs more clearly
- Simplified worker cards to show only essential information (removed blank/N/A fields)

### Fixed
- UI jumping issues when jobs start or finish
- Inconsistent time display (now using absolute datetime instead of relative time)
- Redundant job information display across multiple UI sections
- Added missing formatMemory function to properly display worker memory usage
- Fixed worker cards disappearing when jobs are added or processed by improving state management
- Fixed error with undefined estimatedCompletion variable in worker cards
- Fixed issue with undefined job IDs appearing in job tables and never disappearing
- [2025-04-06 20:07] Fixed job time display to use absolute datetime format instead of constantly changing relative time
- [2025-04-06 20:07] Improved job completion time estimation to properly reset for new jobs and handle different date formats
- [2025-04-06 20:10] Fixed inaccurate job completion estimates by tracking actual processing start time separately from job creation time
- [2025-04-06 20:10] Added both creation time and processing start time to worker cards for better transparency
