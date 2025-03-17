/**
 * Messages class for Redis WebSocket communication
 * 
 * This file provides a structured way to create and parse messages for the Redis WebSocket API.
 * It ensures that all messages follow the correct format and have the required fields.
 * 
 * Based on the TypeScript definitions in core/client-types/messages.ts and aligned with
 * the Python implementation in core/message_models.py and core/message_handler.py
 */

class Messages {
    // Message Types - copied from MessageType enum in messages.ts
    static TYPE = {
        // SETUP_MESSAGES
        REGISTER_WORKER: "register_worker",
        WORKER_REGISTERED: "worker_registered",
        CONNECTION_ESTABLISHED: "connection_established",

        // JOB WORKFLOW_MESSAGES
        SUBMIT_JOB: "submit_job",
        JOB_ACCEPTED: "job_accepted",
        JOB_AVAILABLE: "job_available",
        CLAIM_JOB: "claim_job",
        JOB_ASSIGNED: "job_assigned",
        UPDATE_JOB_PROGRESS: "update_job_progress",
        COMPLETE_JOB: "complete_job",
        FAIL_JOB: "fail_job",

        // STATUS_MESSAGES
        REQUEST_JOB_STATUS: "request_job_status",
        RESPONSE_JOB_STATUS: "response_job_status",

        // GENERAL STATUS MESSAGES
        REQUEST_STATS: "request_stats",
        RESPONSE_STATS: "response_stats",
        SUBSCRIBE_STATS: "subscribe_stats",
        SUBSCRIPTION_CONFIRMED: "subscription_confirmed",
        STATS_BROADCAST: "stats_broadcast",

        // JOB SPECIFIC MESSAGES
        SUBSCRIBE_JOB: "subscribe_job",
        JOB_NOTIFICATIONS_SUBSCRIBED: "job_notifications_subscribed",

        // Worker Status Messages
        WORKER_HEARTBEAT: "worker_heartbeat",
        WORKER_STATUS: "worker_status",
        JOB_UPDATE: "job_update",
        JOB_COMPLETED: "job_completed",

        // Acknowledgment Messages
        ACK: "ack",
        UNKNOWN: "unknown",
        ERROR: "error"
    };

    /**
     * Helper function to generate a timestamp if not provided
     * @param {number} timestamp - Optional timestamp to use
     * @returns {number} - Current timestamp in milliseconds
     */
    static getTimestamp(timestamp) {
        return timestamp || Date.now();
    }

    /**
     * Validates that a message has all required fields
     * @param {Object} message - The message to validate
     * @param {Array<string>} requiredFields - List of required field names
     * @returns {boolean} - True if valid, throws error if invalid
     */
    static validateMessage(message, requiredFields) {
        if (!message || typeof message !== 'object') {
            throw new Error('Invalid message: must be an object');
        }
        
        for (const field of requiredFields) {
            if (message[field] === undefined) {
                throw new Error(`Missing required field: ${field} in message type: ${message.type || 'unknown'}`);
            }
        }
        return true;
    }

    // ==========================================
    // OUTGOING MESSAGE FACTORY METHODS
    // ==========================================

    /**
     * Create a message to submit a new job
     * @param {string} jobType - Type of job to submit
     * @param {number} priority - Priority of the job (higher = more important)
     * @param {Object} payload - Job payload data
     * @param {number} timestamp - Optional timestamp
     * @returns {Object} - Formatted submit job message
     */
    static createSubmitJobMessage(jobType, priority, payload, timestamp) {
        return {
            type: this.TYPE.SUBMIT_JOB,
            job_type: jobType,
            priority: priority || 0,
            payload: payload || {},
            timestamp: this.getTimestamp(timestamp)
        };
    }

    /**
     * Create a message to request job status
     * @param {string} jobId - ID of the job to check
     * @param {number} timestamp - Optional timestamp
     * @returns {Object} - Formatted request job status message
     */
    static createRequestJobStatusMessage(jobId, timestamp) {
        return {
            type: this.TYPE.REQUEST_JOB_STATUS,
            job_id: jobId,
            timestamp: this.getTimestamp(timestamp)
        };
    }

    /**
     * Create a message to request system statistics
     * @param {number} timestamp - Optional timestamp
     * @returns {Object} - Formatted request stats message
     */
    static createRequestStatsMessage(timestamp) {
        return {
            type: this.TYPE.REQUEST_STATS,
            timestamp: this.getTimestamp(timestamp)
        };
    }

    /**
     * Create a message to subscribe to stats updates
     * @param {boolean} enabled - Whether to enable or disable subscription
     * @param {number} timestamp - Optional timestamp
     * @returns {Object} - Formatted subscribe stats message
     */
    static createSubscribeStatsMessage(enabled, timestamp) {
        return {
            type: this.TYPE.SUBSCRIBE_STATS,
            enabled: enabled !== false, // Default to true if not specified
            timestamp: this.getTimestamp(timestamp)
        };
    }

    /**
     * Create a message to subscribe to job updates
     * @param {string} jobId - ID of the job to subscribe to
     * @param {number} timestamp - Optional timestamp
     * @returns {Object} - Formatted subscribe job message
     */
    static createSubscribeJobMessage(jobId, timestamp) {
        return {
            type: this.TYPE.SUBSCRIBE_JOB,
            job_id: jobId,
            timestamp: this.getTimestamp(timestamp)
        };
    }

    // ==========================================
    // INCOMING MESSAGE PARSER METHODS
    // ==========================================

    /**
     * Parse a job accepted message
     * @param {Object} message - Raw message from server
     * @returns {Object} - Parsed job accepted data
     * @throws {Error} - If message is invalid
     */
    static parseJobAcceptedMessage(message) {
        this.validateMessage(message, ['type', 'job_id', 'status']);
        
        if (message.type !== this.TYPE.JOB_ACCEPTED) {
            throw new Error(`Invalid message type: ${message.type}, expected: ${this.TYPE.JOB_ACCEPTED}`);
        }
        
        return {
            jobId: message.job_id,
            status: message.status,
            position: message.position,
            estimatedStart: message.estimated_start,
            timestamp: message.timestamp
        };
    }

    /**
     * Parse a job status message
     * @param {Object} message - Raw message from server
     * @returns {Object} - Parsed job status data
     * @throws {Error} - If message is invalid
     */
    static parseJobStatusMessage(message) {
        this.validateMessage(message, ['type', 'job_id', 'status']);
        
        if (message.type !== this.TYPE.RESPONSE_JOB_STATUS) {
            throw new Error(`Invalid message type: ${message.type}, expected: ${this.TYPE.RESPONSE_JOB_STATUS}`);
        }
        
        return {
            jobId: message.job_id,
            status: message.status,
            progress: message.progress,
            workerId: message.worker_id,
            startedAt: message.started_at,
            completedAt: message.completed_at,
            result: message.result,
            message: message.message,
            timestamp: message.timestamp
        };
    }

    /**
     * Parse a job update message
     * @param {Object} message - Raw message from server
     * @returns {Object} - Parsed job update data
     * @throws {Error} - If message is invalid
     */
    static parseJobUpdateMessage(message) {
        this.validateMessage(message, ['type', 'job_id', 'status']);
        
        if (message.type !== this.TYPE.JOB_UPDATE) {
            throw new Error(`Invalid message type: ${message.type}, expected: ${this.TYPE.JOB_UPDATE}`);
        }
        
        return {
            jobId: message.job_id,
            status: message.status,
            priority: message.priority,
            position: message.position,
            progress: message.progress,
            eta: message.eta,
            message: message.message,
            timestamp: message.timestamp
        };
    }

    /**
     * Parse a job completed message
     * @param {Object} message - Raw message from server
     * @returns {Object} - Parsed job completed data
     * @throws {Error} - If message is invalid
     */
    static parseJobCompletedMessage(message) {
        this.validateMessage(message, ['type', 'job_id', 'status']);
        
        if (message.type !== this.TYPE.JOB_COMPLETED) {
            throw new Error(`Invalid message type: ${message.type}, expected: ${this.TYPE.JOB_COMPLETED}`);
        }
        
        return {
            jobId: message.job_id,
            status: message.status,
            priority: message.priority,
            position: message.position,
            result: message.result,
            timestamp: message.timestamp
        };
    }
    
    /**
     * Parse a complete job message (sent when a job is completed by a worker)
     * @param {Object} message - Raw message from server
     * @returns {Object} - Parsed complete job data
     * @throws {Error} - If message is invalid
     */
    static parseCompleteJobMessage(message) {
        this.validateMessage(message, ['type', 'job_id', 'worker_id']);
        
        if (message.type !== this.TYPE.COMPLETE_JOB) {
            throw new Error(`Invalid message type: ${message.type}, expected: ${this.TYPE.COMPLETE_JOB}`);
        }
        
        return {
            jobId: message.job_id,
            workerId: message.worker_id,
            result: message.result || {},
            timestamp: message.timestamp
        };
    }

    /**
     * Parse an update job progress message
     * @param {Object} message - Raw message from server
     * @returns {Object} - Parsed job progress data
     * @throws {Error} - If message is invalid
     */
    static parseUpdateJobProgressMessage(message) {
        this.validateMessage(message, ['type', 'job_id', 'worker_id', 'progress']);
        
        if (message.type !== this.TYPE.UPDATE_JOB_PROGRESS) {
            throw new Error(`Invalid message type: ${message.type}, expected: ${this.TYPE.UPDATE_JOB_PROGRESS}`);
        }
        
        return {
            jobId: message.job_id,
            workerId: message.worker_id,
            progress: message.progress,
            status: message.status || 'processing',
            message: message.message,
            timestamp: message.timestamp
        };
    }

    /**
     * Parse a stats response message
     * @param {Object} message - Raw message from server
     * @returns {Object} - Parsed stats data
     * @throws {Error} - If message is invalid
     */
    static parseStatsResponseMessage(message) {
        this.validateMessage(message, ['type', 'stats']);
        
        if (message.type !== this.TYPE.RESPONSE_STATS) {
            throw new Error(`Invalid message type: ${message.type}, expected: ${this.TYPE.RESPONSE_STATS}`);
        }
        
        return {
            stats: message.stats,
            timestamp: message.timestamp
        };
    }

    /**
     * Parse a stats broadcast message
     * @param {Object} message - Raw message from server
     * @returns {Object} - Parsed stats broadcast data
     * @throws {Error} - If message is invalid
     */
    static parseStatsBroadcastMessage(message) {
        // Only validate the message type, as the structure has connections, workers, system directly
        this.validateMessage(message, ['type']);
        
        if (message.type !== this.TYPE.STATS_BROADCAST) {
            throw new Error(`Invalid message type: ${message.type}, expected: ${this.TYPE.STATS_BROADCAST}`);
        }
        
        // Return the full message structure as it contains all the stats data
        // The structure has connections, workers, system fields instead of a single stats field
        return {
            connections: message.connections || {},
            workers: message.workers || {},
            system: message.system || {},
            subscriptions: message.subscriptions || {},
            timestamp: message.timestamp
        };
    }
    
    /**
     * Parse a request stats message
     * @param {Object} message - Raw message from client
     * @returns {Object} - Parsed request stats message
     * @throws {Error} - If message is invalid
     */
    static parseRequestStatsMessage(message) {
        this.validateMessage(message, ['type']);
        
        if (message.type !== this.TYPE.REQUEST_STATS) {
            throw new Error(`Invalid message type: ${message.type}, expected: ${this.TYPE.REQUEST_STATS}`);
        }
        
        return {
            type: message.type,
            timestamp: message.timestamp
        };
    }

    /**
     * Parse a worker status message
     * @param {Object} message - Raw message from server
     * @returns {Object} - Parsed worker status data
     * @throws {Error} - If message is invalid
     */
    static parseWorkerStatusMessage(message) {
        this.validateMessage(message, ['type', 'worker_id']);
        
        if (message.type !== this.TYPE.WORKER_STATUS) {
            throw new Error(`Invalid message type: ${message.type}, expected: ${this.TYPE.WORKER_STATUS}`);
        }
        
        return {
            workerId: message.worker_id,
            status: message.status,
            capabilities: message.capabilities,
            timestamp: message.timestamp
        };
    }

    /**
     * Parse an error message
     * @param {Object} message - Raw message from server
     * @returns {Object} - Parsed error data
     * @throws {Error} - If message is invalid
     */
    static parseErrorMessage(message) {
        this.validateMessage(message, ['type', 'error']);
        
        if (message.type !== this.TYPE.ERROR) {
            throw new Error(`Invalid message type: ${message.type}, expected: ${this.TYPE.ERROR}`);
        }
        
        return {
            error: message.error,
            details: message.details,
            timestamp: message.timestamp
        };
    }

    /**
     * Parse any message based on its type
     * @param {Object} message - Raw message from server
     * @returns {Object} - Parsed message data
     * @throws {Error} - If message type is unknown or invalid
     */
    static parseMessage(message) {
        if (!message || typeof message !== 'object') {
            throw new Error('Invalid message: must be an object');
        }

        if (!message.type) {
            throw new Error('Invalid message: missing type field');
        }

        // Parse based on message type
        switch (message.type) {
            case this.TYPE.JOB_ACCEPTED:
                return this.parseJobAcceptedMessage(message);
            case this.TYPE.RESPONSE_JOB_STATUS:
                return this.parseJobStatusMessage(message);
            case this.TYPE.JOB_UPDATE:
                return this.parseJobUpdateMessage(message);
            case this.TYPE.JOB_COMPLETED:
                return this.parseJobCompletedMessage(message);
            case this.TYPE.COMPLETE_JOB:
                return this.parseCompleteJobMessage(message);
            case this.TYPE.UPDATE_JOB_PROGRESS:
                return this.parseUpdateJobProgressMessage(message);
            case this.TYPE.RESPONSE_STATS:
                return this.parseStatsResponseMessage(message);
            case this.TYPE.STATS_BROADCAST:
                return this.parseStatsBroadcastMessage(message);
            case this.TYPE.REQUEST_STATS:
                return this.parseRequestStatsMessage(message);
            case this.TYPE.WORKER_STATUS:
                return this.parseWorkerStatusMessage(message);
            case this.TYPE.WORKER_REGISTERED:
                return this.parseWorkerRegisteredMessage(message);
            case this.TYPE.FAIL_JOB:
                return this.parseFailJobMessage(message);
            case this.TYPE.ERROR:
                return this.parseErrorMessage(message);
            case this.TYPE.CONNECTION_ESTABLISHED:
                return { connected: true, message: message.message, timestamp: message.timestamp };
            case this.TYPE.ACK:
                return this.parseAckMessage(message);
            default:
                // For unknown message types, return a standardized unknown message format
                return {
                    type: message.type,
                    originalMessage: message,
                    timestamp: message.timestamp || this.getTimestamp()
                };

        }
    }

    /**
     * Parse an acknowledgment message
     * @param {Object} message - Raw message from server
     * @returns {Object} - Parsed acknowledgment data
     * @throws {Error} - If message is invalid
     */
    static parseAckMessage(message) {
        this.validateMessage(message, ['type', 'original_id', 'original_type']);
        
        if (message.type !== this.TYPE.ACK) {
            throw new Error(`Invalid message type: ${message.type}, expected: ${this.TYPE.ACK}`);
        }
        
        return {
            originalId: message.original_id,
            originalType: message.original_type,
            timestamp: message.timestamp
        };
    }

    /**
     * Parse a worker registered message
     * @param {Object} message - Raw message from server
     * @returns {Object} - Parsed worker registered data
     * @throws {Error} - If message is invalid
     */
    static parseWorkerRegisteredMessage(message) {
        this.validateMessage(message, ['type', 'worker_id']);
        
        if (message.type !== this.TYPE.WORKER_REGISTERED) {
            throw new Error(`Invalid message type: ${message.type}, expected: ${this.TYPE.WORKER_REGISTERED}`);
        }
        
        return {
            workerId: message.worker_id,
            capabilities: message.capabilities || [],
            timestamp: message.timestamp
        };
    }

    /**
     * Parse a fail job message
     * @param {Object} message - Raw message from server
     * @returns {Object} - Parsed fail job data
     * @throws {Error} - If message is invalid
     */
    static parseFailJobMessage(message) {
        this.validateMessage(message, ['type', 'job_id', 'worker_id']);
        
        if (message.type !== this.TYPE.FAIL_JOB) {
            throw new Error(`Invalid message type: ${message.type}, expected: ${this.TYPE.FAIL_JOB}`);
        }
        
        return {
            jobId: message.job_id,
            workerId: message.worker_id,
            error: message.error || 'Unknown error',
            details: message.details || {},
            timestamp: message.timestamp
        };
    }

    /**
     * Create a custom error message
     * @param {string} errorMessage - Error message
     * @param {Object} details - Additional error details
     * @param {number} timestamp - Optional timestamp
     * @returns {Object} - Formatted error message
     */
    static createErrorMessage(errorMessage, details, timestamp) {
        return {
            type: this.TYPE.ERROR,
            error: errorMessage,
            details: details || {},
            timestamp: this.getTimestamp(timestamp)
        };
    }
}

// Export the Messages class
if (typeof module !== 'undefined' && module.exports) {
    module.exports = Messages;
}
