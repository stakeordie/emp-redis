#!/usr/bin/env python3
# Base message type definitions
import time
from typing import Dict, Any, Optional, List, Union
from pydantic import BaseModel, Field, field_validator

# WebSocket message types

# PROPOSED NAMING CONVENTION FOR MESSAGE TYPES
# ----------------------------------------
# We are considering a more descriptive naming convention for message types
# that clearly indicates the sender, action, subject, and receiver of each message.
# 
# Proposed format: <SENDER>_<VERB>_<SUBJECT>_<STATUS/DETAIL>_TO_<RECEIVER>
# 
# Where:
# - <SENDER>: Who is sending the message (CLIENT, WORKER, SERVER, MONITOR)
# - <VERB>: The action being performed in present tense (SUBMIT, CONFIRM, ANNOUNCE)
# - <SUBJECT>: What the message is about (JOB, STATS, HEARTBEAT)
# - <STATUS/DETAIL>: Additional context about the subject (ACCEPTED, COMPLETED, FAILED)
# - <RECEIVER>: Who is receiving the message (SERVER, CLIENT, WORKER, WORKERS)
#
# Examples of how current message types would map to the new convention:
# - SUBMIT_JOB → CLIENT_SUBMIT_JOB_NEW_TO_SERVER
# - JOB_ACCEPTED → SERVER_CONFIRM_JOB_ACCEPTED_TO_CLIENT
# - WORKER_HEARTBEAT → WORKER_SEND_HEARTBEAT_STATUS_TO_SERVER
# - JOB_AVAILABLE → SERVER_ANNOUNCE_JOB_AVAILABLE_TO_WORKERS
# - CLAIM_JOB → WORKER_CLAIM_JOB_REQUEST_TO_SERVER
# - JOB_COMPLETED → SERVER_NOTIFY_JOB_COMPLETED_TO_CLIENT
#
# This naming convention provides clear indication of message flow and purpose,
# making the codebase more maintainable and easier to understand.
# 
# NOTE: This is a proposal only. No changes have been made to the actual message types yet.
# Implementation would require coordinated updates across Python and TypeScript code.

class MessageType:

    # SETUP_MESSAGES

    #7 WORKER_REGISTER_WITH_SERVER
    REGISTER_WORKER = "register_worker"             # Worker → Server: Registers itself with the server to receive jobs

    #7 SERVER_CONFIRM_REGISTERED_TO_WORKER
    WORKER_REGISTERED = "worker_registered"        # Server → Worker: Confirms that a worker has been registered

    #8 WORKER_SEND_MY_HEARTBEAT_TO_SERVER
    WORKER_HEARTBEAT = "worker_heartbeat"          # Worker → Server: Sends periodic heartbeat to indicate it's still alive

    #8 WORKER_SEND_MY_STATUS_TO_SERVER
    WORKER_STATUS = "worker_status"                # Worker → Server: Reports its current status (busy, idle, etc.)

    #0 SERVER_SEND_CONNECTION_ESTABLISHED_TO_CLIENT
    CONNECTION_ESTABLISHED = "connection_established"   # Server → Client/Worker: Confirms that a WebSocket connection has been established



    #JOB WORKFLOW_MESSAGES

    # CLIENT_SUBMIT_JOB_TO_SERVER
    SUBMIT_JOB = "submit_job"                           # Client → Server: Submits a new job to the server for processing

    #SERVER_CONFIRM_JOB_ACCEPTED_TO_CLIENT
    JOB_ACCEPTED = "job_accepted"                       # Server → Client: Acknowledges that a job has been accepted for processing

    #SERVER_BROADCAST_JOB_AVAILABLE_TO_WORKERS
    JOB_AVAILABLE = "job_available"                # Server → Worker: Notifies workers that a job is available for processing

    #WORKER_CLAIM_JOB_REQUEST_TO_SERVER
    CLAIM_JOB = "claim_job"                         # Worker → Server: Attempts to claim a job for processing

    #SERVER_BROADCAST_JOB_ASSIGNED_TO_THE_WORKER
    JOB_ASSIGNED = "job_assigned"                  # Server → Worker: Assigns a job to a worker

    #UPDATE_JOB_PROGRESS_TO_SERVER

    #6 WORKER_SEND_JOB_COMPLETION_TO_SERVER
    COMPLETE_JOB = "complete_job"                   # Worker → Server -> Client: Notifies that a job has been completed successfully

    #WORKER_SEND_JOB_FAILURE_TO_SERVER
    FAIL_JOB = "fail_job"                           # Worker → Server: Notifies that a job has failed

    #SERVER_SEND_JOB_COMPLETION_ACK_TO_WORKER
    JOB_COMPLETED_ACK = "job_completed_ack"         # Server → Worker: Acknowledges receipt of a job completion message

    # STATUS_MESSAGES

    #CLIENT_REQUEST_JOB_STATUS_FROM_SERVER
    #1 Renamed from GET_JOB_STATUS to follow a consistent request-response naming pattern
    REQUEST_JOB_STATUS = "request_job_status"       # Client → Server: Requests the current status of a specific job
    #1 Keep the old name for backward compatibility
    RESPONSE_JOB_STATUS = "response_job_status"    # Server → Client: Responds with the current status of a requested job

    #GENERAL STATUS MESSAGES

    #2 CLIENT_REQUEST_ALL_STATS_FROM_SERVER
    REQUEST_STATS = "request_stats"                 # Client → Server: Requests system statistics

    #2 SERVER_SEND_STATS_TO_CLIENT
    RESPONSE_STATS = "response_stats"              # Server → Client: Responds with system statistics
    
    #3 CLIENT_SUBSCRIBE_ALL_STATS_FROM_SERVER
    SUBSCRIBE_STATS = "subscribe_stats"             # Client → Server: Subscribes to receive periodic system statistics

    #SERVER_CONFIRM_SUBSCRIPTION_TO_CLIENT
    SUBSCRIPTION_CONFIRMED = "subscription_confirmed"   # Server → Client: Confirms a client's subscription request

    #3 SERVER_BROADCAST_STATS_TO_CLIENTS
    STATS_BROADCAST = "stats_broadcast"            # Server → Clients: Broadcasts system statistics to subscribed clients

    #JOB SPECIFIC MESSAGES

    #4 CLIENT_SUBSCRIBE_JOB_ALERTS_FROM_SERVER
    SUBSCRIBE_JOB = "subscribe_job"                 # Client → Server: Subscribes to receive updates for a specific job

    #4 SERVER_CONFIRM_JOB_NOTIFICATIONS_SUBSCRIBED_TO_CLIENT
    JOB_NOTIFICATIONS_SUBSCRIBED = "job_notifications_subscribed"   # Server → Client: Confirms subscription to job notifications
    
    # WORKER_SUBSCRIBE_JOB_NOTIFICATIONS_FROM_SERVER
    SUBSCRIBE_JOB_NOTIFICATIONS = "subscribe_job_notifications"  # Worker → Server: Subscribes to receive job notifications

    #WORKER_SEND_JOB_PROGRESS
    UPDATE_JOB_PROGRESS = "update_job_progress"     # Worker → Server -> Client: Updates the progress of a job it's processing


    # Acknowledgment Messages

    # SERVER_ACK
    ACK = "ack"       

    # SERVER_UNKNOWN
    UNKNOWN = "unknown"   # Server → Client/Worker: Used when a message type cannot be determined

    #SERVER_SEND_JOB_ERROR_TO_CLIENT
    ERROR = "error"                                # Server → Client/Worker: Reports an error condition

# Base message class for all messages
class BaseMessage(BaseModel):
    """Base class for all message types"""
    type: str
    timestamp: float = Field(default_factory=time.time)