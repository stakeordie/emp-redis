# Changelog

All notable changes to the EMP Redis project will be documented in this file.

## [Unreleased]

### Added
- [2025-04-06 20:21] Enhanced Redis hub to send all job progress information to monitors, including client IDs
- [2025-04-06 20:21] Modified job completion notifications to also be sent to all monitors with client ID information

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
