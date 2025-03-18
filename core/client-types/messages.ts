/**
 * TypeScript definitions for Emp-Redis message types
 *
 * This file provides type definitions for all messages exchanged between
 * clients, workers, and the Redis Hub. It mirrors the Python models defined
 * in core/models.py.
 */

/**
 * All possible message types in the system
 *
 * PROPOSED NAMING CONVENTION FOR MESSAGE TYPES
 * ----------------------------------------
 * We are considering a more descriptive naming convention for message types
 * that clearly indicates the sender, action, subject, and receiver of each message.
 *
 * Proposed format: <SENDER>_<VERB>_<SUBJECT>_<STATUS/DETAIL>_TO_<RECEIVER>
 *
 * Where:
 * - <SENDER>: Who is sending the message (CLIENT, WORKER, SERVER, MONITOR)
 * - <VERB>: The action being performed in present tense (SUBMIT, CONFIRM, ANNOUNCE)
 * - <SUBJECT>: What the message is about (JOB, STATS, HEARTBEAT)
 * - <STATUS/DETAIL>: Additional context about the subject (ACCEPTED, COMPLETED, FAILED)
 * - <RECEIVER>: Who is receiving the message (SERVER, CLIENT, WORKER, WORKERS)
 *
 * Examples of how current message types would map to the new convention:
 * - SUBMIT_JOB → CLIENT_SUBMIT_JOB_NEW_TO_SERVER
 * - JOB_ACCEPTED → SERVER_CONFIRM_JOB_ACCEPTED_TO_CLIENT
 * - WORKER_HEARTBEAT → WORKER_SEND_HEARTBEAT_STATUS_TO_SERVER
 * - JOB_AVAILABLE → SERVER_ANNOUNCE_JOB_AVAILABLE_TO_WORKERS
 * - CLAIM_JOB → WORKER_CLAIM_JOB_REQUEST_TO_SERVER
 * - JOB_COMPLETED → SERVER_NOTIFY_JOB_COMPLETED_TO_CLIENT
 *
 * This naming convention provides clear indication of message flow and purpose,
 * making the codebase more maintainable and easier to understand.
 *
 * NOTE: This is a proposal only. No changes have been made to the actual message types yet.
 * Implementation would require coordinated updates across Python and TypeScript code.
 */
export enum MessageType {
  // SETUP_MESSAGES
  REGISTER_WORKER = "register_worker", // Worker → Server: Registers itself with the server to receive jobs
  WORKER_REGISTERED = "worker_registered", // Server → Worker: Confirms successful worker registration
  CONNECTION_ESTABLISHED = "connection_established", // Server → Client/Worker: Confirms that a WebSocket connection has been established

  // JOB WORKFLOW_MESSAGES
  SUBMIT_JOB = "submit_job", // Client → Server: Submits a new job to the server for processing
  JOB_ACCEPTED = "job_accepted", // Server → Client: Confirms that a job has been accepted for processing
  JOB_AVAILABLE = "job_available", // Server → Workers: Announces that a job is available for processing
  CLAIM_JOB = "claim_job", // Worker → Server: Claims a job for processing
  JOB_ASSIGNED = "job_assigned", // Server → Worker: Assigns a job to a worker
  UPDATE_JOB_PROGRESS = "update_job_progress", // Worker → Server -> Client: Updates the progress of a job it's processing
  COMPLETE_JOB = "complete_job", // Worker → Server -> Client: Notifies that a job has been completed successfully
  FAIL_JOB = "fail_job", // Worker → Server: Notifies that a job has failed

  // STATUS_MESSAGES
  // 1. Renamed from GET_JOB_STATUS to follow a consistent request-response naming pattern
  REQUEST_JOB_STATUS = "request_job_status", // Client → Server: Requests the current status of a specific job
  // 1. Renamed from JOB_STATUS to follow a consistent request-response naming pattern
  RESPONSE_JOB_STATUS = "response_job_status", // Server → Client: Responds with the current status of a requested job                  // Alias for RESPONSE_JOB_STATUS (backward compatibility)

  // GENERAL STATUS MESSAGES
  // 2. Renamed from REQUEST_STATS to follow a consistent request-response naming pattern
  REQUEST_STATS = "request_stats", // Client → Server: Requests system statistics
  // 2. Renamed from STATS_RESPONSE to follow a consistent request-response naming pattern
  RESPONSE_STATS = "response_stats", // Server → Client: Responds with system statistics

  // 3. CLIENT_SUBSCRIBE_ALL_STATS_FROM_SERVER
  SUBSCRIBE_STATS = "subscribe_stats", // Client → Server: Subscribes to receive periodic system statistics
  // SERVER_CONFIRM_SUBSCRIPTION_TO_CLIENT
  SUBSCRIPTION_CONFIRMED = "subscription_confirmed", // Server → Client: Confirms a client's subscription request
  // 3. SERVER_BROADCAST_STATS_TO_CLIENTS
  STATS_BROADCAST = "stats_broadcast", // Server → Clients: Broadcasts system statistics to subscribed clients

  // JOB SPECIFIC MESSAGES
  // 4. CLIENT_SUBSCRIBE_JOB_ALERTS_FROM_SERVER
  SUBSCRIBE_JOB = "subscribe_job", // Client → Server: Subscribes to receive updates for a specific job
  // 4. SERVER_CONFIRM_JOB_NOTIFICATIONS_SUBSCRIBED_TO_CLIENT
  JOB_NOTIFICATIONS_SUBSCRIBED = "job_notifications_subscribed", // Server → Client: Confirms subscription to job notifications

  // Worker Status Messages
  WORKER_HEARTBEAT = "worker_heartbeat",
  WORKER_STATUS = "worker_status",
  JOB_UPDATE = "job_update",
  JOB_COMPLETED = "job_completed",

  // Acknowledgment Messages
  ACK = "ack",
  UNKNOWN = "unknown",
  ERROR = "error",
}

/**
 * Base interface for all messages
 */
export interface BaseMessage {
  type: string;
  timestamp?: number;
}

/**
 * Job model for job submission
 */
export interface Job {
  id: string;
  type: string;
  priority: number;
  params: Record<string, any>;
  client_id?: string;
  timestamp?: number;
}

/**
 * Worker identification for job processing
 */
export interface WorkerInfo {
  machine_id: string;
  gpu_id: number;
  worker_id?: string;
  timestamp?: number;
}

// Client to Server Messages

/**
 * Message to submit a new job
 */
export interface SubmitJobMessage extends BaseMessage {
  type: MessageType.SUBMIT_JOB;
  job_type: string;
  priority: number;
  payload: Record<string, any>;
  timestamp?: number;
}

/**
 * Message to get the status of a job
 */
export interface GetJobStatusMessage extends BaseMessage {
  type: MessageType.REQUEST_JOB_STATUS;
  job_id: string;
  timestamp?: number;
}

/**
 * Message to register a worker
 */
export interface RegisterWorkerMessage extends BaseMessage {
  type: MessageType.REGISTER_WORKER;
  machine_id: string;
  gpu_id: number;
  timestamp?: number;
}

/**
 * Message to update job progress
 *
 * This message is used for both worker-to-server and server-to-client communication
 * regarding job progress updates.
 */
export interface UpdateJobProgressMessage extends BaseMessage {
  type: MessageType.UPDATE_JOB_PROGRESS;
  job_id: string;
  worker_id: string;
  progress: number; // Value between 0-100
  status: string; // Default: "processing"
  message?: string;
  timestamp?: number;
}

/**
 * Message to mark a job as completed
 */
export interface CompleteJobMessage extends BaseMessage {
  type: MessageType.COMPLETE_JOB;
  job_id: string;
  machine_id: string;
  gpu_id: number;
  result?: Record<string, any>;
  timestamp?: number;
}

// Server to Client Messages

/**
 * Message indicating a job has been accepted
 */
export interface JobAcceptedMessage extends BaseMessage {
  type: MessageType.JOB_ACCEPTED;
  job_id: string;
  status: string;
  position?: number;
  estimated_start?: string;
  notified_workers?: number;
  timestamp?: number;
}

/**
 * Message with job status information
 */
export interface JobStatusMessage extends BaseMessage {
  type: MessageType.RESPONSE_JOB_STATUS;
  job_id: string;
  status: string;
  progress?: number;
  worker_id?: string;
  started_at?: number;
  completed_at?: number;
  result?: Record<string, any>;
  message?: string;
  timestamp?: number;
}

/**
 * Message with job update information
 */
export interface JobUpdateMessage extends BaseMessage {
  type: MessageType.JOB_UPDATE;
  job_id: string;
  status: string;
  priority?: number;
  position?: number;
  progress?: number;
  eta?: string;
  message?: string;
  timestamp?: number;
}

/**
 * Message indicating a job has been assigned to a worker
 */
export interface JobAssignedMessage extends BaseMessage {
  type: MessageType.JOB_ASSIGNED;
  job_id: string;
  worker_id: string;
  job_type: string;
  priority: number;
  params: Record<string, any>;
  timestamp?: number;
}

/**
 * Message indicating a job has been completed
 */
export interface JobCompletedMessage extends BaseMessage {
  type: MessageType.JOB_COMPLETED;
  job_id: string;
  status: string;
  priority?: number;
  position?: number;
  result?: Record<string, any>;
  timestamp?: number;
}

/**
 * Error message
 */
export interface ErrorMessage extends BaseMessage {
  type: MessageType.ERROR;
  error: string;
  details?: Record<string, any>;
  timestamp?: number;
}

/**
 * Message indicating a worker has been registered
 */
export interface WorkerRegisteredMessage extends BaseMessage {
  type: MessageType.WORKER_REGISTERED;
  worker_id: string;
  status: string;
  timestamp?: number;
}

// Stats Messages

/**
 * Message to subscribe to stats updates
 */
export interface SubscribeStatsMessage extends BaseMessage {
  type: MessageType.SUBSCRIBE_STATS;
  enabled: boolean;
  timestamp?: number;
}

/**
 * Message to request current stats
 */
export interface GetStatsMessage extends BaseMessage {
  type: MessageType.REQUEST_STATS;
  timestamp?: number;
}

/**
 * Message to subscribe to job updates
 */
export interface SubscribeJobMessage extends BaseMessage {
  type: MessageType.SUBSCRIBE_JOB;
  job_id: string;
  timestamp?: number;
}

// Worker Messages

/**
 * Worker heartbeat message
 */
export interface WorkerHeartbeatMessage extends BaseMessage {
  type: MessageType.WORKER_HEARTBEAT;
  worker_id: string;
  status?: string;
  load?: number;
  timestamp?: number;
}

/**
 * Legacy worker heartbeat message - REMOVED
 * @deprecated Use WorkerHeartbeatMessage instead
 */
// Legacy heartbeat message removed - use WorkerHeartbeatMessage instead

/**
 * Worker status message
 */
export interface WorkerStatusMessage extends BaseMessage {
  type: MessageType.WORKER_STATUS;
  worker_id: string;
  status?: string;
  capabilities?: Record<string, any>;
  timestamp?: number;
}

/**
 * Message to claim a job
 */
export interface ClaimJobMessage extends BaseMessage {
  type: MessageType.CLAIM_JOB;
  worker_id: string;
  job_id: string;
  claim_timeout?: number;
  timestamp?: number;
}

/**
 * JobClaimedMessage removed - functionality handled by JobAssignedMessage
 */

/**
 * Message to subscribe to job notifications - REMOVED
 * @deprecated Workers automatically receive job notifications
 */
// SubscribeJobNotificationsMessage removed - workers automatically receive job notifications

// Status Request/Response Messages

/**
 * Request job status message
 */
export interface RequestJobStatusMessage extends BaseMessage {
  type: MessageType.REQUEST_JOB_STATUS;
  job_id: string;
  timestamp?: number;
}

/**
 * Response job status message
 */
export interface ResponseJobStatusMessage extends BaseMessage {
  type: MessageType.RESPONSE_JOB_STATUS;
  job_id: string;
  status: string;
  progress?: number;
  result?: Record<string, any>;
  error?: string;
  timestamp?: number;
}

/**
 * Request stats message
 */
export interface RequestStatsMessage extends BaseMessage {
  type: MessageType.REQUEST_STATS;
  timestamp?: number;
}

/**
 * Response stats message
 */
export interface ResponseStatsMessage extends BaseMessage {
  type: MessageType.RESPONSE_STATS;
  stats: Record<string, any>;
  timestamp?: number;
}

// Backward compatibility interfaces

/**
 * Get job status message (alias for RequestJobStatusMessage)
 * @deprecated Use RequestJobStatusMessage instead
 */
export interface GetJobStatusMessage extends BaseMessage {
  type: MessageType.REQUEST_JOB_STATUS;
  job_id: string;
  timestamp?: number;
}

/**
 * Job status message (alias for ResponseJobStatusMessage)
 * @deprecated Use ResponseJobStatusMessage instead
 */
export interface JobStatusMessage extends BaseMessage {
  type: MessageType.RESPONSE_JOB_STATUS;
  job_id: string;
  status: string;
  progress?: number;
  result?: Record<string, any>;
  error?: string;
  timestamp?: number;
}

/**
 * Get stats message (alias for RequestStatsMessage)
 * @deprecated Use RequestStatsMessage instead
 */
export interface GetStatsMessage extends BaseMessage {
  type: MessageType.REQUEST_STATS;
  timestamp?: number;
}

/**
 * Stats response message (alias for ResponseStatsMessage)
 * @deprecated Use ResponseStatsMessage instead
 */
export interface StatsResponseMessage extends BaseMessage {
  type: MessageType.RESPONSE_STATS;
  stats: Record<string, any>;
  timestamp?: number;
}

// Job Notification Messages

/**
 * Message indicating a job is available
 */
export interface JobAvailableMessage extends BaseMessage {
  type: MessageType.JOB_AVAILABLE;
  job_id: string;
  job_type: string;
  priority?: number;
  params_summary?: Record<string, any>;
  timestamp?: number;
}

/**
 * Connection established message
 */
export interface ConnectionEstablishedMessage extends BaseMessage {
  type: MessageType.CONNECTION_ESTABLISHED;
  message: string;
  timestamp?: number;
}

/**
 * Union type of all possible messages
 */
/**
 * Message for a failed job
 */
export interface FailJobMessage extends BaseMessage {
  type: MessageType.FAIL_JOB;
  job_id: string;
  worker_id: string;
  error: string;
  timestamp?: number;
}

/**
 * Stats response message
 */
export interface StatsResponseMessage extends BaseMessage {
  type: MessageType.RESPONSE_STATS;
  stats: Record<string, any>;
  timestamp?: number;
}

/**
 * Message for acknowledging receipt of a message
 */
export interface AckMessage extends BaseMessage {
  type: MessageType.ACK;
  message_id?: string;
  original_type?: string;
  timestamp?: number;
}

/**
 * Message for unknown message types
 */
export interface UnknownMessage extends BaseMessage {
  type: MessageType.UNKNOWN;
  content: string;
  timestamp?: number;
}

export type Message =
  | SubmitJobMessage
  | GetJobStatusMessage
  | RegisterWorkerMessage
  | UpdateJobProgressMessage
  | CompleteJobMessage
  | FailJobMessage
  | JobAcceptedMessage
  | JobStatusMessage
  | JobUpdateMessage
  | JobAssignedMessage
  | JobCompletedMessage
  | ErrorMessage
  | WorkerRegisteredMessage
  | SubscribeStatsMessage
  | GetStatsMessage
  | SubscribeJobMessage
  | WorkerHeartbeatMessage
  | WorkerStatusMessage
  | ClaimJobMessage
  | RequestJobStatusMessage
  | ResponseJobStatusMessage
  | RequestStatsMessage
  | ResponseStatsMessage
  | GetJobStatusMessage
  | JobStatusMessage
  | GetStatsMessage
  | StatsResponseMessage
  | JobAvailableMessage
  | ConnectionEstablishedMessage
  | AckMessage
  | UnknownMessage;

/**
 * Type guard to check if a message is of a specific type
 * @param message The message to check
 * @param type The message type to check for
 * @returns True if the message is of the specified type
 */
export function isMessageType<T extends Message>(
  message: Message,
  type: MessageType
): message is T {
  return message.type === type;
}
