# Changelog

All notable changes to the EMP Redis project will be documented in this file.

## [Unreleased]

### Fixed
- [2025-05-26T23:40:47-04:00] Reverted monitor.js to stable version from previous commit to resolve UI issues:
  - Removed recent changes that were causing TypeError exceptions
  - Restored stable job tracking and worker status handling
  - Simplified progress bar display to ensure reliability
  - Returned to proven implementation for job-worker relationship tracking
- [2025-05-26T23:45:00-04:00] Fixed progress bar display and worker status tracking issues:
  - Enhanced job progress handling to ensure numeric progress values
  - Fixed worker status not updating properly after job completion
  - Added proper type conversion for progress values
  - Improved job status transitions between states
  - Ensured completed jobs always show 100% progress
  - Fixed worker status synchronization with job status
  - Added detailed logging for job and worker state changes

- [2025-05-26T23:30:00-04:00] Fixed TypeError exceptions in monitor UI when accessing undefined values:
  - Added null checks to all substring() calls throughout the codebase
  - Improved error handling for job ID display in the UI
  - Fixed job progress display to handle undefined job IDs gracefully
  - Enhanced error message formatting to handle various error types
  - Prevented UI errors when processing chunked messages with missing IDs

- [2025-05-26T23:25:00-04:00] Implemented comprehensive job-worker linking system to fix persistent job status issues:
  - Added intelligent job assignment for busy workers with no explicit job ID
  - Implemented automatic linking of pending jobs to busy workers
  - Enhanced worker status handler to properly update job states
  - Added detailed job state transition logging for debugging
  - Fixed edge cases where workers showed busy but jobs remained in queue
  - Added bidirectional job-worker relationship enforcement
  - Ensured processingStartedAt timestamp is properly set for all jobs
  - Implemented job state reconciliation for inconsistent states

- [2025-05-26T23:20:00-04:00] Fixed job queue display issue where jobs remained in queue despite worker being busy:
  - Enhanced job queue filtering to handle all queue status variations ('pending', 'queued', 'accepted')
  - Added worker assignment check to remove jobs from queue when assigned to a worker
  - Improved active jobs detection to include any job with a worker_id assigned
  - Added detailed state logging for job assignments to track status transitions
  - Fixed inconsistency between worker busy state and job queue display
  - Ensured jobs with status 'accepted' are properly handled in the UI

- [2025-05-26T22:35:00-04:00] Improved job state tracking and debugging in monitor UI:
  - Removed excessive console logs to reduce noise and improve performance
  - Added focused job state tracking logs with consistent format
  - Added clear job state change indicators with before/after state information
  - Implemented job state summary logging for easier debugging
  - Added job-worker link tracking to diagnose assignment issues
  - Improved readability of console output for easier troubleshooting

- [2025-05-26T21:45:00-04:00] Fixed job status updates not reflecting correctly in monitor UI:
  - Added explicit handler for job_assigned messages in monitor.js
  - Implemented proper job-worker linking when jobs are assigned
  - Fixed issue where jobs remained in queue instead of showing as processing
  - Added detailed logging for job assignment events
  - Ensured worker status is updated to 'busy' when assigned a job
  - Fixed worker's current_job_id tracking to properly link jobs to workers

- [2025-05-26T21:25:00-04:00] Fixed critical connection issues in hub and worker services:
  - Added missing 'os' and 'time' module imports in connection_manager.py
  - Added missing 'time' module import in base_worker.py
  - Fixed send_to_worker method to directly access worker_connections dictionary
  - Fixed connector_loader to properly skip base connector classes
  - Fixed A1111 connector authentication:
    - Implemented custom _get_headers method for A1111 connector
    - Added proper UTF-8 encoding for authentication credentials
    - Enhanced authentication debugging with detailed logging
    - Added response body and headers logging for authentication failures
  - Improved exception handling in A1111 health check method
  - Resolved worker registration errors and connection handling
  - Fixed chunk cleanup error in BaseWorker

### Added
- [2025-05-26T20:55:00-04:00] Enhanced simple Redis monitor with payload template system:
  - Added payload template dropdown to select between different payloads for the same job type
  - Created a1111_chunked_test template with oversized payload to trigger chunking
  - Added dynamic template discovery based on job type
  - Implemented automatic UI updates when job type changes
  - Added large prompt and negative prompt fields to force message chunking
  - Included test metadata for tracking chunked message processing
  - Designed to test real-world chunked message scenarios with A1111 connector

- [2025-05-26T19:30:00-04:00] Implemented robust chunked message handling system:
  - Added hash-based chunking mechanism for large WebSocket messages
  - Implemented chunk storage and reassembly in BaseWorker
  - Added periodic cleanup of stale chunked messages
  - Synchronized chunk format between ConnectionManager and BaseWorker
  - Ensured data integrity through hash verification
  - Fixed WebSocket message size limitations for large payloads
  - Added detailed logging for chunk processing and debugging

- [2025-05-26T18:15:00-04:00] Fixed WebSocket message size issues for A1111 connector:
  - Increased message size limit from 1MB to 10MB for WebSocket communications
  - Added base64 image stripping in service request messages to reduce message size
  - Fixed "Message too large to send" errors with large payloads
  - Fixed "sent 1009 (message too big)" errors in worker connections
  - Improved logging for large message detection and handling
- [2025-05-26T16:25:00-04:00] Added ServiceRequestMessage class and message type:
  - Defined SERVICE_REQUEST message type in MessageType enum
  - Created ServiceRequestMessage class with proper fields
  - Added parsing support in MessageModels.parse_message
  - Ensures proper handling of service requests from A1111 connector
  - Fixed issue with service request messages not being properly recognized

- [2025-05-26T16:22:00-04:00] Added service_request message handler to message_handler.py:
  - Added dedicated case for handling service_request messages in handle_worker_message
  - Implemented proper message conversion and validation
  - Added forwarding to monitors via broadcast_to_monitors
  - Added conditional debug logging controlled by DEBUG_LOGS environment variable
  - Fixed "Unsupported message type: service_request" errors
- [2025-05-25T10:15:00-04:00] Extended service request broadcasting to A1111 connector:
  - A1111 connector now broadcasts requests sent to the A1111 service
  - Added broadcast_service_request method to A1111 connector
  - Includes endpoint, method, URL, and payload information in broadcasts
  - Enables visibility into what's being sent to the A1111 service
  - Helps with debugging and understanding A1111 service requests

- [2025-05-24T14:00:00-04:00] Added service request broadcasting feature:
  - Workers now broadcast their communications with end services (like ComfyUI)
  - Added new Service Requests section to monitor interface to display these communications
  - Allows viewing the exact content of requests being sent to services
  - Helps with debugging and understanding what's being requested from services

### Changed
- [2025-05-25T23:55:00-04:00] Fixed RESTSyncConnector to remove default 'rest' job type:
  - Removed 'rest' as default job_type in the base connector class
  - Improved type safety with proper string annotations
  - Added comprehensive documentation for concrete subclasses
  - Enhanced error messages to guide proper implementation
  - Ensured job_type must match connector_id for proper job assignment
  - Fixed root cause of A1111 connector job assignment issues

- [2025-05-25T21:55:00-04:00] Fixed A1111 connector job type mismatch causing job assignment issues:
  - Ensured job_type always matches connector_id in A1111Connector
  - Modified get_job_type() to always return connector_id
  - Prevented environment variables from causing mismatches
  - Added safeguards to maintain job_type/connector_id consistency
  - Fixed critical issue preventing A1111 jobs from being assigned to the worker

- [2025-05-25T21:51:00-04:00] Fixed JobFailedMessage import and usage in base_worker.py:
  - Changed import from JobFailedMessage to FailJobMessage to match deployment environment
  - Updated references in send_job_failed method
  - Fixed critical import error preventing worker startup
  - Used debug level logging to identify the exact issue

- [2025-05-25T21:45:00-04:00] Fixed worker import paths to match deployment environment structure:
  - Updated import in base_worker.py from `core.core_types.message_models` to `core.message_models`
  - Enhanced diagnostic logging to provide detailed environment information
  - Added file existence checks and content inspection for key files
  - Used debug level for diagnostic messages to facilitate cleanup
  - Fixed critical import error preventing worker startup

- [2025-05-25T22:15:00-04:00] Fixed connector loading with backward compatibility:
  - Simplified connector class finding logic in connector_loader.py
  - Added connector_id property to all connector classes including simulation_connector
  - Added fallback to connector_name for backward compatibility
  - Improved error handling and debugging in connector loading
  - Fixed "Could not find connector class with connector_id" errors
  - Reduced excessive logging in base_worker.py

- [2025-05-25T18:45:00-04:00] Fixed remaining type errors in worker_main.py and apps/comfy-worker/scripts/a1111/docker/config.py:
  - Added null checks for worker_base in worker_main.py to prevent "None not callable" errors
  - Fixed Dict and Any imports in config.py
  - Added proper type casting for JSON data in config.py
  - Added string type conversion for replacement values in replace_if_invalid function
  - Added detailed error messages and logging for better debugging
  - Ensured all functions return the correct types as declared in their signatures

- [2025-05-25T18:15:00-04:00] Fixed "None not callable" errors in worker.py and base_worker.py:
  - Added explicit null checks before calling BaseWorker constructor
  - Added type checks to ensure BaseWorker is callable before instantiation
  - Added null checks for load_connectors and get_worker_capabilities functions
  - Improved error messages with detailed information about the type errors
  - Added timestamps to all error logs for better traceability

- [2025-05-25T17:50:00-04:00] Fixed type errors in connector_loader.py:
  - Simplified ConnectorInterface import structure to avoid redefinition errors
  - Added proper null checks for ModuleSpec to prevent attribute access errors
  - Added type annotation for CONNECTOR_DEPENDENCIES dictionary
  - Fixed "Cannot assign to a type" errors by using intermediate variables
  - Added null checks for connector_capabilities to prevent iteration errors
  - Added detailed comments with timestamps for traceability

- [2025-05-25T17:00:00-04:00] Fixed type errors in WebSocketConnector base class:
  - Simplified ConnectorInterface import structure to avoid redefinition errors
  - Added null checks for WebSocket connection before accessing attributes
  - Ensured _get_connection_url always returns a string to match declared return type
  - Added detailed comments with timestamps for traceability
  - Improved error handling with better logging for edge cases

- [2025-05-25T16:40:00-04:00] Fixed type errors in ComfyUI connector:
  - Simplified WebSocketConnector import structure to fix type compatibility
  - Changed connector_name to None to match base class type
  - Fixed ClientWSTimeout parameter usage in WebSocket connections
  - Added null checks for execution_start to prevent subtraction errors
  - Ensured proper return types for send_workflow and _process_service_job functions
  - Improved error handling with detailed logging

- [2025-05-25T15:05:00-04:00] Improved logging system across core components:
  - Changed warning logs to error logs for better visibility of issues
  - Removed unnecessary info and debug logging statements
  - Added timestamps to all error logs for better traceability
  - Converted verbose logging to code comments to maintain documentation
  - Improved error reporting for invalid message formats
  - Reduced log noise for routine operations

- [2025-05-25T15:00:00-04:00] Fixed type errors in message handler:
  - Fixed incompatible type error for forward_job_completion by converting CompleteJobMessage to dict
  - Ensured job_type is always a string for JobAvailableMessage
  - Added proper null checks and default values
  - Added detailed comments with timestamps for traceability

- [2025-05-24T13:12:00-04:00] Improved UI layout and scrolling behavior:
  - Created vertical layout with Connected Workers, Job Queue, and Finished Jobs stacked vertically
  - Added fixed heights with scrolling for all sections to prevent layout shifts
  - Implemented consistent scrolling behavior across all sections
  - Improved responsive design for better mobile experience
  - Reorganized UI elements to prioritize worker status information

### Fixed
- [2025-05-25T09:45:00-04:00] Fixed issue requiring double-click on job details buttons:
  - Implemented event delegation for job action buttons
  - Fixed event binding to properly handle dynamically added elements
  - Improved click handling to respond to the first click
  - Added proper event propagation handling
  - Enhanced button styling for better user feedback

- [2025-05-24T12:52:00-04:00] Fixed date formatting functions to handle all date formats:
  - Added robust error handling to formatDate and formatDateTime functions
  - Fixed TypeError when displaying job details with invalid date formats
  - Added support for Unix timestamps in seconds and milliseconds
  - Improved error reporting and fallback display for invalid dates
  - Added detailed comments explaining the date handling logic

- [2025-05-24T12:49:00-04:00] Standardized element naming in monitor.js:
  - Changed all instances of jobTypeDropdown to jobType for consistency
  - Documented duplicate jobPayload element references with clear comments
  - Added modal elements to the elements object for better organization
  - Updated modal functionality to use the elements object for consistency
  - Added detailed comments explaining all changes
  - Improved code maintainability by clarifying naming conflicts

- [2025-05-24T12:47:00-04:00] Improved button layout and functionality:
  - Added details button to active jobs table to match finished jobs table
  - Created horizontal flex container for action buttons to improve layout
  - Standardized all buttons to use onclick attributes for consistency
  - Added proper styling for action buttons with hover effects
  - Fixed details button functionality to ensure modal opens correctly

### Added
- [2025-05-24T13:01:00-04:00] Improved REST API response display:
  - Added maximize button to REST API response container
  - Implemented modal for better JSON viewing with syntax highlighting
  - Added copy to clipboard functionality with visual feedback
  - Added keyboard shortcuts (Escape to close, Ctrl+C to copy)
  - Fixed scrolling issues in the REST API response container
  - Made inner text area scrollable while keeping outer container fixed
  - Improved styling with monospace font and better visual hierarchy
  - Enhanced user experience for viewing large JSON payloads

- [2025-05-24T11:56:00-04:00] Added job payload to API response:
  - Added payload field to JobStatusResponse model
  - Updated get_job_status endpoint to include original job payload in response
  - Enables viewing the original job parameters when checking job status
  - Improves debugging and monitoring capabilities
- [2025-05-23T19:49:23-04:00] Fixed job position numbering to use 0-based indexing:
  - Reverted backend position calculation to use natural 0-based indexing
  - Updated frontend to properly display 0-based positions (0 = next up, 1 = one job ahead, etc.)
  - Fixed position descriptions to be consistent with the 0-based approach
  - Improved user experience by showing clearer queue position information
- [2025-05-23T09:47:30-04:00] Increased WebSocket message size limits:
  - Added standardized message size configuration using MAX_WS_MESSAGE_SIZE_MB environment variable
  - Set default message size limit to 100MB for all WebSocket connections
  - Added proper error handling for large messages
  - Enhanced logging for message size tracking
- [2025-05-23T08:48:00-04:00] Fixed missing connector_statuses field in WorkerStatusMessage class:
  - Added connector_statuses field to the WorkerStatusMessage model
  - Fixed error "Unexpected keyword argument 'connector_statuses' for 'WorkerStatusMessage'"
  - Ensured worker status updates can include connector status information
  - Added timestamp and detailed comments for future reference

- [2025-05-23T08:47:00-04:00] Fixed WebSocket message size errors by completing worker tracking transition:
  - Completed transition from Redis-based worker tracking to in-memory tracking
  - Fixed inconsistency in `update_worker_capabilities` method that was still writing to Redis
  - Updated `get_all_workers_status` to return empty dict and prevent large WebSocket messages
  - Added `cleanup_stale_worker_records` method to remove stale worker records from Redis
  - Added automatic cleanup during system initialization
  - Fixed WebSocket error 1009 (message too large) caused by stale worker records
- [2025-05-21T00:04:00-04:00] Enhanced message type handling in job completion flow:
  - Updated forward_job_completion to handle both dictionaries and CompleteJobMessage objects
  - Added support for Pydantic model serialization in monitor messages
  - Improved type detection and conversion for different message formats
  - Added robust fallback mechanisms for unexpected message types
  - Fixed issue with complete_job messages not being sent

- [2025-05-20T23:52:00-04:00] Fixed bytes/string handling in result logging:
  - Improved handling of binary data in log messages
  - Added proper decoding of bytes to strings with error handling
  - Fixed string concatenation issues with bytes objects
  - Enhanced result preview generation with type-specific handling
  - Added fallback representation for binary data

- [2025-05-20T23:51:00-04:00] Fixed type compatibility in message handling:
  - Replaced dictionaries with proper CompleteJobMessage objects
  - Updated message_handler.py to create proper message objects
  - Modified connection_manager.py to convert dictionaries to message objects
  - Added robust error handling for message creation
  - Fixed mypy type errors with send_to_client method

- [2025-05-20T23:49:00-04:00] Fixed type checking issues in connection handling:
  - Added proper type checking for message attributes in send_to_client
  - Enhanced forward_job_completion with robust type validation
  - Added default values to prevent None values in string contexts
  - Improved error handling for invalid message types
  - Fixed mypy type errors related to job_id handling

- [2025-05-20T23:35:00-04:00] Implemented direct job completion message sending:
  - Added direct sending of complete_job messages in handle_complete_job
  - Implemented new forward_job_completion method in ConnectionManager
  - Added comprehensive error handling and logging
  - Fixed issue with job completion messages not being sent
  - Ensured messages are sent only after successful result storage

- [2025-05-20T21:35:00-04:00] Fixed job completion message handling:
  - Used asyncio.to_thread to properly await the synchronous complete_job method
  - Added detailed error handling and logging for the thread execution
  - Ensured proper sequencing of job completion operations
  - Fixed issue with job completion messages not being sent reliably

- [2025-05-20T21:29:00-04:00] Eliminated duplicate job update messages:
  - Modified RedisService.update_job_progress to not publish redundant updates
  - Modified RedisService.complete_job to not publish redundant updates
  - Preserved the more detailed messages with connector details
  - Improved message flow efficiency by removing unnecessary duplicates
  - Fixed issue with duplicate "started" and "completed" messages
- [2025-05-20T21:20:00-04:00] Fixed job completion message sequence:
  - Modified RedisService.complete_job to ensure result storage completes before publishing updates
  - Updated MessageHandler.handle_complete_job to properly await result storage
  - Removed direct message sending to rely on the correct message flow
  - Added detailed logging to track the job completion process
  - Fixed timing issues that caused empty result data in complete_job messages
- [2025-05-20T20:58:00-04:00] Implemented direct job completion message sending:
  - Added direct complete_job message sending in handle_complete_job method
  - Ensured complete_job messages are sent immediately after storing results in Redis
  - Enhanced logging to track message flow and delivery
  - Fixed timing issues with job completion notification
  - Added redundant message paths to ensure reliable delivery
- [2025-05-20T19:25:00-04:00] Fixed job completion message flow to ensure correct order of operations:
  - Moved complete_job message generation from connection_manager.py to message_handler.py
  - Ensured job result data is properly stored in Redis before sending complete_job messages
  - Added proper type checking and handling for different result data formats
  - Eliminated duplicate complete_job messages
  - Improved logging to track message flow and data processing
- [2025-05-20T19:17:00-04:00] Enhanced job result data handling in connection_manager.py and message_handler.py:
  - Added robust type checking for result data retrieved from Redis
  - Improved handling of different result formats (dictionary, string, bytes)
  - Added detailed logging of result data processing steps
  - Fixed JSON parsing errors by properly detecting when data is already a dictionary
  - Ensured consistent result data format in complete_job messages
- [2025-05-20T17:55:00-04:00] Fixed job subscription mechanism to properly deliver complete_job messages:
  - Changed job subscriptions to support multiple clients per job
  - Added fallback to send to all connected clients when no subscriptions exist
  - Implemented proper cleanup of subscriptions when clients disconnect
  - Added detailed logging for subscription management

- [2025-05-20T17:37:00-04:00] Improved job result data handling in WebSocket messages:
  - Implemented direct worker data approach in message_handler.py
  - Eliminated Redis query timing issues by using data directly from worker
  - Disabled duplicate complete_job messages in connection_manager.py
  - Ensured base64 image data is properly included in WebSocket messages
  - Added detailed logging for job result data processing

- [2025-05-20T17:19:00-04:00] Removed external dependencies in connection_manager.py:
  - Replaced external API calls with direct Redis access
  - Eliminated dependency on requests library
  - Maintained retry mechanism with increasing delays
  - Improved deployment reliability by reducing external dependencies

- [2025-05-20T17:13:30-04:00] Fixed logger import in connection_manager.py:
  - Changed direct loguru import to use project's custom logger from utils.logger
  - Resolved deployment error caused by missing loguru dependency
  - Ensured consistent logger usage across the codebase

- [2025-05-20T17:10:00-04:00] Enhanced job data retrieval with retry mechanism:
  - Added retry logic with increasing delays (1s, 2s, 3s) to ensure job data is fully saved to Redis
  - Implemented detailed logging to track job result data retrieval and processing
  - Added base64 image detection to verify output data is properly included in messages
  - Fixed type errors in connection_manager.py for better reliability
  - Improved error handling for API requests to Redis server
  - This ensures WebSocket messages include complete job data with base64 images
- 2025-04-28-21:33 - Improved job completion messaging system:
  - Simplified `complete_job` method in RedisService to only send standard status updates
  - Enhanced `handle_job_update` in MessageHandler to detect completed status and send an additional explicit message
  - Implemented direct WebSocket delivery of "complete_job" messages after status updates
  - Added detailed logging for message flow and delivery confirmation
  - Maintained backward compatibility with existing update_job_progress messages
  - This ensures clients reliably receive explicit job completion notifications in the correct order
- 2025-04-26-21:30 - Added job cancellation functionality:
  - Added `cancel_job` method to RedisService to permanently cancel jobs
  - Added `CancelJobMessage` class and message type
  - Added handler for job cancellation requests in MessageHandler
  - Jobs can now be manually cancelled with a reason
  - Cancellation removes jobs from the queue and updates their status
  - Added detailed logging for job cancellation events

- 2025-04-25-23:55 - Implemented in-memory worker failure tracking:
  - Added `worker_failed_jobs` dictionary to ConnectionManager to track which workers have failed which jobs
  - Modified job notification logic to check in-memory state instead of Redis for worker exclusion
  - Simplified Redis service by removing Redis-based worker filtering
  - Added detailed logging for worker exclusion decisions
  - This improves job reassignment by ensuring failed jobs are never reassigned to workers that previously failed them
- 2025-04-25-22:51 - Enhanced logging and job notification for worker reassignment:
  - Added detailed worker capability tracking in job notifications
  - Added comprehensive logging to identify why workers aren't claiming jobs
  - Improved job notification messages with more metadata
  - Added checks for other available workers when a claim is rejected
  - Added explicit warning messages in notifications to prevent failed workers from claiming jobs

- 2025-04-25-19:22 - Critical fix for worker_id field in claim_job method:
  - Fixed inconsistency where claim_job was setting "worker" field instead of "worker_id"
  - Added both fields for backward compatibility
  - Added detailed logging for worker assignment
  - This resolves the root cause of the job reassignment issue where last_failed_worker wasn't being set
- 2025-04-25-19:17 - Additional robustness improvements for job reassignment logic:
  - Fixed bug in fail_job where retry_count was referenced before assignment
  - Added defensive handling for worker_id being None when setting last_failed_worker
  - Added type conversion for Redis values to ensure proper string handling
  - Added comprehensive boxed logging for all edge cases in the job failure path
  - Added constants for DEFAULT_MAX_RETRIES and DEFAULT_JOB_PRIORITY

- 2025-04-25-19:03 - Critical fix for job reassignment logic - final solution:
  - Fixed issue where last_failed_worker field was being lost during job requeuing
  - Implemented atomic update of job status while preserving last_failed_worker field
  - Used hmset instead of individual hset calls to ensure field consistency
  - Resolved issue where the same worker was repeatedly assigned failed jobs

- 2025-04-25-18:58 - Fixed critical issue with job reassignment logic:
  - Enhanced fail_job method to track and preserve last_failed_worker field during requeuing
  - Added comprehensive job state verification in notify_idle_workers_of_job
  - Added detailed logging to track last_failed_worker field throughout job lifecycle
  - Fixed issue where last_failed_worker field was not being preserved during job requeuing

- 2025-04-25-18:55 - Added connection manager diagnostic logging for job reassignment verification:
  - Enhanced send_to_worker method to extract and log last_failed_worker field
  - Added detailed boxed logging showing serialized message content
  - Added explicit verification of last_failed_worker field presence in outgoing messages
  - Improved traceability of job reassignment logic across system components
- 2025-04-25-18:45 - Added comprehensive diagnostic logging for job reassignment logic:
  - Added eye-catching boxed logs showing the exact structure of job notification messages
  - Added detailed logging of message attributes, types, and raw content
  - Implemented multiple message parsing strategies with explicit logging
  - Added clear visualization of extracted job notification values
  - Enhanced notification message logging to show when last_failed_worker is included
- 2025-04-25-18:40 - Fixed worker-side filtering to ensure jobs are never reassigned to the same worker:
  - Enhanced message parsing in handle_job_notification to reliably extract last_failed_worker field
  - Added multiple fallback methods to access last_failed_worker from different message formats
  - Added detailed debug logging of message structure and attributes
  - Improved notification message creation to explicitly include last_failed_worker only when it exists
- 2025-04-25-18:35 - Enhanced job reassignment system with worker-side filtering:
  - Added last_failed_worker to job notification messages
  - Updated worker to check last_failed_worker and ignore jobs it previously failed
  - Added eye-catching log entries for job notification filtering
  - This provides a second layer of protection against job reassignment to failed workers
- 2025-04-25-18:20 - Fixed job notification system to exclude workers that previously failed a job:
  - Modified notify_idle_workers_of_job to check the last_failed_worker field
  - Added worker filtering to prevent notification to workers that previously failed a job
  - Added eye-catching log entries for worker exclusion decisions
  - Added warning when all idle workers have been excluded due to previous failures
- 2025-04-25-18:10 - Fixed job reassignment logic to properly prevent failed jobs from being reassigned to the same worker:
  - Fixed comparison by converting bytes to string for last_failed_worker
  - Added detailed debug logging to help diagnose worker reassignment issues
  - Added eye-catching log entries for worker reassignment decisions
- 2025-04-25-18:05 - Added eye-catching log entries for connection attempts and results:
  - Added boxed log entries with clear SUCCESS/FAILED indicators
  - Added visual indicators (✓✓✓/✗✗✗) to make success and failure states immediately visible
  - Added detailed connection information in all log entries
- 2025-04-25-18:00 - Enhanced WebSocketConnector and ComfyUIConnector to immediately fail jobs when connection issues are detected
- 2025-04-25-17:55 - Optimized connection timeouts for faster failure detection:
  - Reduced initial connection timeout to 5 seconds in WebSocketConnector
  - Reduced connection validation timeout to 3 seconds in ComfyUIConnector
  - Reduced workflow sending timeout to 5 seconds for faster failure detection
  - Increased message waiting timeout to 60 seconds after successful connection
- 2025-04-25-17:55 - Improved connection validation to properly detect and report connection failures
- 2025-04-25-17:45 - Updated WebSocketConnector to always raise exceptions for connection failures instead of returning False
- 2025-04-25-15:35 - Added improved error handling in ComfyUIConnector to test connection and fail jobs quickly when ComfyUI server is unreachable
- 2025-04-25-15:20 - Added job reassignment logic to prevent failed jobs from being reassigned to the same worker
- [2025-04-25 15:35] Improved ComfyUI connector error handling:
  - Added actual connection testing during initialization
  - Added timeout for connection attempts
  - Added pre-job connection validation
  - Improved error messages for connection failures
  - Fixed issue with jobs getting stuck when ComfyUI server is unreachable
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
