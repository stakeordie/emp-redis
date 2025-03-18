#!/usr/bin/env python3
# Implementation of the MessageModelsInterface
import json
import time
import uuid
from typing import Dict, Any, Optional, List, TypeVar, Callable, Union
from pydantic import BaseModel, Field, field_validator
from .interfaces.message_models_interface import MessageModelsInterface
from .utils.logger import logger

# Import base message types from core_types module
from .core_types.base_messages import (
    BaseMessage,
    MessageType
)

# Client to Server Messages
class SubmitJobMessage(BaseMessage):
    type: str = MessageType.SUBMIT_JOB
    job_type: str
    priority: int = 0
    payload: Dict[str, Any]
    timestamp: float = Field(default_factory=time.time)
    
    @field_validator('priority')
    def validate_priority(cls, v):
        if v < 0 or v > 10:
            raise ValueError("Priority must be between 0 and 10")
        return v

# Renamed from GetJobStatusMessage to follow a consistent request-response naming pattern
class RequestJobStatusMessage(BaseMessage):
    type: str = MessageType.REQUEST_JOB_STATUS
    job_id: str
    timestamp: float = Field(default_factory=time.time)

# Renamed from GetStatsMessage to follow a consistent request-response naming pattern
class RequestStatsMessage(BaseMessage):
    type: str = MessageType.REQUEST_STATS
    timestamp: float = Field(default_factory=time.time)

class SubscribeStatsMessage(BaseMessage):
    type: str = MessageType.SUBSCRIBE_STATS
    enabled: bool = True
    timestamp: float = Field(default_factory=time.time)

class SubscribeJobMessage(BaseMessage):
    type: str = MessageType.SUBSCRIBE_JOB
    job_id: str
    timestamp: float = Field(default_factory=time.time)


# Worker to Server Messages
class RegisterWorkerMessage(BaseMessage):
    type: str = MessageType.REGISTER_WORKER
    worker_id: str
    capabilities: Optional[Dict[str, Any]] = None
    subscribe_to_jobs: bool = True  # Default to subscribing to job notifications
    status: str = "idle"  # Default status is idle
    timestamp: float = Field(default_factory=time.time)

class UpdateJobProgressMessage(BaseMessage):
    type: str = MessageType.UPDATE_JOB_PROGRESS
    job_id: str
    worker_id: str
    progress: int
    status: str = "processing"
    message: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)
    
    @field_validator('progress')
    def validate_progress(cls, v):
        """Validate that progress is between 0 and 100 inclusive."""
        if v < 0 or v > 100:
            raise ValueError("Progress must be between 0 and 100")
        return v

class ClaimJobMessage(BaseMessage):
    type: str = MessageType.CLAIM_JOB
    worker_id: str
    job_id: str
    claim_timeout: Optional[int] = 30
    timestamp: float = Field(default_factory=time.time)

class CompleteJobMessage(BaseMessage):
    type: str = MessageType.COMPLETE_JOB
    job_id: str
    worker_id: str
    result: Optional[Dict[str, Any]] = None
    timestamp: float = Field(default_factory=time.time)

class JobCompletedAckMessage(BaseMessage):
    """Message for acknowledging receipt of a job completion message"""
    type: str = MessageType.JOB_COMPLETED_ACK
    job_id: str
    worker_id: str
    timestamp: float = Field(default_factory=time.time)

class FailJobMessage(BaseMessage):
    type: str = MessageType.FAIL_JOB
    job_id: str
    worker_id: str
    error: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)


# Worker Heartbeat and Status Messages
class WorkerHeartbeatMessage(BaseMessage):
    type: str = MessageType.WORKER_HEARTBEAT
    worker_id: str
    status: Optional[str] = "idle"
    load: Optional[float] = 0.0
    timestamp: float = Field(default_factory=time.time)
    
class WorkerStatusMessage(BaseMessage):
    type: str = MessageType.WORKER_STATUS
    message_id: Optional[str] = None
    worker_id: str
    status: Optional[str] = "idle"
    capabilities: Optional[Dict[str, Any]] = None
    timestamp: float = Field(default_factory=time.time)

# SubscribeJobNotificationsMessage has been removed
# Its functionality is now part of RegisterWorkerMessage
    

# Server to Client Messages
class SubscriptionConfirmedMessage(BaseMessage):
    """Message for confirming subscription to job status updates or monitor channels"""
    type: str = MessageType.SUBSCRIPTION_CONFIRMED
    job_id: str
    monitor_id: Optional[str] = None
    channels: Optional[List[str]] = None
    timestamp: float = Field(default_factory=time.time)

class JobNotificationsSubscribedMessage(BaseMessage):
    """Message for confirming subscription to job notifications"""
    type: str = MessageType.JOB_NOTIFICATIONS_SUBSCRIBED
    worker_id: str
    timestamp: float = Field(default_factory=time.time)

class JobAcceptedMessage(BaseMessage):
    type: str = MessageType.JOB_ACCEPTED
    job_id: str
    status: str = "pending"
    position: Optional[int] = None
    estimated_start: Optional[str] = None
    notified_workers: Optional[int] = 0
    timestamp: float = Field(default_factory=time.time)

# Renamed from JobStatusMessage to follow a consistent request-response naming pattern
class ResponseJobStatusMessage(BaseMessage):
    type: str = MessageType.RESPONSE_JOB_STATUS
    job_id: str
    status: str
    progress: Optional[int] = None
    worker_id: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)

class JobCompletedMessage(BaseMessage):
    type: str = MessageType.COMPLETE_JOB
    job_id: str
    status: str = "completed"
    priority: Optional[int] = None
    position: Optional[int] = None
    result: Optional[Dict[str, Any]] = None
    timestamp: float = Field(default_factory=time.time)

class ErrorMessage(BaseMessage):
    type: str = MessageType.ERROR
    error: str
    details: Optional[Dict[str, Any]] = None
    timestamp: float = Field(default_factory=time.time)

class WorkerRegisteredMessage(BaseMessage):
    type: str = MessageType.WORKER_REGISTERED
    worker_id: str
    status: str = "active"
    timestamp: float = Field(default_factory=time.time)

# Job Notification Messages
class JobAvailableMessage(BaseMessage):
    type: str = MessageType.JOB_AVAILABLE
    job_id: str
    job_type: str
    priority: Optional[int] = 0
    job_request_payload: Optional[Dict[str, Any]] = None
    timestamp: float = Field(default_factory=time.time)

class JobAssignedMessage(BaseMessage):
    type: str = MessageType.JOB_ASSIGNED
    job_id: str
    worker_id: str
    job_type: str
    priority: int
    params: Dict[str, Any]
    timestamp: float = Field(default_factory=time.time)


# Monitor to Server
# Renamed from StatsResponseMessage to follow a consistent request-response naming pattern
class ResponseStatsMessage(BaseMessage):
    type: str = MessageType.RESPONSE_STATS
    stats: Dict[str, Any]
    timestamp: float = Field(default_factory=time.time)

# Server to Monitor
class StatsBroadcastMessage(BaseMessage):
    """Message for broadcasting comprehensive system status to monitors"""
    type: str = MessageType.STATS_BROADCAST
    message_id: Optional[str] = None
    connections: Dict[str, List[str]]
    workers: Dict[str, Dict[str, Any]]
    subscriptions: Dict[str, Any]
    system: Optional[Dict[str, Any]] = None


# Connections All
class ConnectionEstablishedMessage(BaseMessage):
    type: str = MessageType.CONNECTION_ESTABLISHED
    message: str = "Connection established"

# Acknowledgment Messages
class AckMessage(BaseMessage):
    """Message for acknowledging receipt of a message"""
    type: str = MessageType.ACK
    message_id: Optional[str] = None
    original_id: str
    original_type: Optional[str] = None

class UnknownMessage(BaseMessage):
    """Message for unknown message types"""
    type: str = MessageType.UNKNOWN
    content: str

class MessageModels(MessageModelsInterface):
    """
    Implementation of the MessageModelsInterface.
    
    This class provides concrete implementations of the message model
    creation and validation methods defined in the interface.
    """
    T = TypeVar('T', bound=BaseMessage)
    
    def _try_parse_message(self, create_func: Callable[[], T], message_type: str) -> Optional[T]:
        """
        Helper method to safely parse a message with consistent error handling.
        
        Args:
            create_func: A function that creates and returns a message object
            message_type: The type of message being parsed (for error logging)
            

            Optional[T]: The parsed message object or None if parsing failed
        """
        try:
            return create_func()
        except Exception as e:
            logger.error(f"Error parsing {message_type} message: {e}")
            return None
    
    def parse_message(self, data: Dict[str, Any]) -> Optional[BaseMessage]:
        """
        Parse incoming message data into appropriate message model.
        
        Args:
            data: Raw message data
            
        Returns:
            Optional[BaseMessage]: Parsed message model if valid, None otherwise
        """
        if not isinstance(data, dict) or "type" not in data:
            return None
        
        message_type = data.get("type")
        
        match(message_type):
            case MessageType.SUBMIT_JOB:
                return self._try_parse_message(
                    lambda: SubmitJobMessage(
                        type=MessageType.SUBMIT_JOB,
                        job_type=data.get("job_type", "unknown"),
                        priority=data.get("priority", 0),
                        payload=data.get("payload", {}),
                        timestamp=data.get("timestamp", time.time())
                    ),
                    message_type
                )
            case MessageType.REQUEST_JOB_STATUS:
                return self._try_parse_message(
                    lambda: RequestJobStatusMessage(
                        type=MessageType.REQUEST_JOB_STATUS,
                        job_id=data.get("job_id", ""),
                        timestamp=data.get("timestamp", time.time())
                    ),
                    message_type
                )
            case MessageType.SUBSCRIBE_JOB:
                return self._try_parse_message(
                    lambda: SubscribeJobMessage(
                        type=MessageType.SUBSCRIBE_JOB,
                        job_id=data.get("job_id", ""),
                        timestamp=data.get("timestamp", time.time())
                    ),
                    message_type
                )
            case MessageType.SUBSCRIBE_STATS:
                return self._try_parse_message(
                    lambda: SubscribeStatsMessage(
                        type=MessageType.SUBSCRIBE_STATS,
                        timestamp=data.get("timestamp", time.time())
                    ),
                    message_type
                )
            case MessageType.REQUEST_STATS:
                return self._try_parse_message(
                    lambda: RequestStatsMessage(
                        type=MessageType.REQUEST_STATS,
                        timestamp=data.get("timestamp", time.time())
                    ),
                    message_type
                )
            case MessageType.CONNECTION_ESTABLISHED:
                return self._try_parse_message(
                    lambda: ConnectionEstablishedMessage(
                        type=MessageType.CONNECTION_ESTABLISHED,
                        message=data.get("message", "Connection established"),
                        timestamp=data.get("timestamp", time.time())
                    ),
                    message_type
                )
            case MessageType.REGISTER_WORKER:
                return self._try_parse_message(
                    lambda: RegisterWorkerMessage(
                        type=MessageType.REGISTER_WORKER,
                        worker_id=data.get("worker_id", ""),
                        timestamp=data.get("timestamp", time.time())
                    ),
                    message_type
                )
            case MessageType.UPDATE_JOB_PROGRESS:
                return self._try_parse_message(
                    lambda: UpdateJobProgressMessage(
                        type=MessageType.UPDATE_JOB_PROGRESS,
                        job_id=data.get("job_id", ""),
                        worker_id=data.get("worker_id", ""),
                        progress=data.get("progress", 0),
                        status=data.get("status", "processing"),
                        message=data.get("message", None),
                        timestamp=data.get("timestamp", time.time())
                    ),
                    message_type
                )
            case MessageType.COMPLETE_JOB:
                return self._try_parse_message(
                    lambda: CompleteJobMessage(
                        type=MessageType.COMPLETE_JOB,
                        job_id=data.get("job_id", ""),
                        worker_id=data.get("worker_id", ""),
                        result=data.get("result", {}),
                        timestamp=data.get("timestamp", time.time())
                    ),
                    message_type
                )
            case MessageType.WORKER_HEARTBEAT:
                return self._try_parse_message(
                    lambda: WorkerHeartbeatMessage(
                        type=MessageType.WORKER_HEARTBEAT,
                        worker_id=data.get("worker_id", ""),
                        status=data.get("status", "idle"),
                        load=data.get("load", 0.0),
                        timestamp=data.get("timestamp", time.time())
                    ),
                    message_type
                )
            case MessageType.WORKER_STATUS:
                return self._try_parse_message(
                    lambda: WorkerStatusMessage(
                        type=MessageType.WORKER_STATUS,
                        message_id=data.get("message_id", None),
                        worker_id=data.get("worker_id", ""),
                        status=data.get("status", "idle"),
                        capabilities=data.get("capabilities", {}),
                        timestamp=data.get("timestamp", time.time())
                    ),
                    message_type
                )
            case MessageType.CLAIM_JOB:
                return self._try_parse_message(
                    lambda: ClaimJobMessage(
                        type=MessageType.CLAIM_JOB,
                        worker_id=data.get("worker_id", ""),
                        job_id=data.get("job_id", ""),
                        claim_timeout=data.get("claim_timeout", 30),
                        timestamp=data.get("timestamp", time.time())
                    ),
                    message_type
                )
            # Server-to-Worker Messages
            case MessageType.JOB_ASSIGNED:
                return self._try_parse_message(
                    lambda: JobAssignedMessage(
                        type=MessageType.JOB_ASSIGNED,
                        job_id=data.get("job_id", ""),
                        worker_id=data.get("worker_id", ""),
                        job_type=data.get("job_type", ""),
                        priority=data.get("priority", 0),
                        params=data.get("params", {}),
                        timestamp=data.get("timestamp", time.time())
                    ),
                    message_type
                )
            case MessageType.JOB_AVAILABLE:
                return self._try_parse_message(
                    lambda: JobAvailableMessage(
                        type=MessageType.JOB_AVAILABLE,
                        job_id=data.get("job_id", ""),
                        job_type=data.get("job_type", ""),
                        priority=data.get("priority", 0),
                        job_request_payload=data.get("job_request_payload", {}),
                        timestamp=data.get("timestamp", time.time())
                    ),
                    message_type
                )
            
            case MessageType.JOB_NOTIFICATIONS_SUBSCRIBED:
                return self._try_parse_message(
                    lambda: JobNotificationsSubscribedMessage(
                        type=MessageType.JOB_NOTIFICATIONS_SUBSCRIBED,
                        worker_id=data.get("worker_id", ""),
                        timestamp=data.get("timestamp", time.time())
                    ),
                    message_type
                )
            case MessageType.WORKER_REGISTERED:
                return self._try_parse_message(
                    lambda: WorkerRegisteredMessage(
                        type=MessageType.WORKER_REGISTERED,
                        worker_id=data.get("worker_id", ""),
                        status=data.get("status", "active"),
                        timestamp=data.get("timestamp", time.time())
                    ),
                    message_type
                )
            # JOB_CLAIMED case removed - functionality handled by JOB_ASSIGNED
            case MessageType.ERROR:
                return self._try_parse_message(
                    lambda: ErrorMessage(
                        type=MessageType.ERROR,
                        error=data.get("error", "Unknown error"),
                        details=data.get("details", None),
                        timestamp=data.get("timestamp", time.time())
                    ),
                    message_type
                )
            case MessageType.FAIL_JOB:
                return self._try_parse_message(
                    lambda: FailJobMessage(
                        type=MessageType.FAIL_JOB,
                        job_id=data.get("job_id", ""),
                        worker_id=data.get("worker_id", ""),
                        error=data.get("error", None),
                        timestamp=data.get("timestamp", time.time())
                    ),
                    message_type
                )
            case _:
                logger.warning(f"Unknown message type: {message_type}")
                return None
    
    def create_error_message(self, error: str, details: Optional[Dict[str, Any]] = None) -> BaseMessage:
        """
        Create an error message.
        
        Args:
            error: Error message
            details: Optional error details
            
        Returns:
            BaseMessage: Error message model
        """
        return ErrorMessage(
            type=MessageType.ERROR,
            error=error,
            details=details
        )
    
    def create_job_accepted_message(self, job_id: str, status: str = "pending", 
                                   position: Optional[int] = None,
                                   estimated_start: Optional[str] = None,
                                   notified_workers: Optional[int] = 0) -> BaseMessage:
        """
        Create a job accepted message.
        
        Args:
            job_id: ID of the accepted job
            status: Job status
            position: Optional position in queue
            estimated_start: Optional estimated start time
            notified_workers: Optional number of workers notified
            
        Returns:
            BaseMessage: Job accepted message model
        """
        return JobAcceptedMessage(
            type=MessageType.JOB_ACCEPTED,
            job_id=job_id,
            status=status,
            position=position,
            estimated_start=estimated_start,
            notified_workers=notified_workers
        )
    
    # Renamed from create_job_status_message to follow a consistent request-response naming pattern
    def create_response_job_status_message(self, job_id: str, status: str, 
                                        progress: Optional[int] = None,
                                        worker_id: Optional[str] = None,
                                        started_at: Optional[float] = None,
                                        completed_at: Optional[float] = None,
                                        result: Optional[Dict[str, Any]] = None,
                                        message: Optional[str] = None) -> BaseMessage:
        """
        Create a job status response message.
        
        Args:
            job_id: ID of the job
            status: Job status
            progress: Optional progress percentage
            worker_id: Optional ID of the worker processing the job
            started_at: Optional timestamp when job started
            completed_at: Optional timestamp when job completed
            result: Optional job result
            message: Optional status message
            
        Returns:
            ResponseJobStatusMessage: Job status response message model
        """
        return ResponseJobStatusMessage(
            type=MessageType.RESPONSE_JOB_STATUS,
            job_id=job_id,
            status=status,
            progress=progress,
            worker_id=worker_id,
            started_at=started_at,
            completed_at=completed_at,
            result=result,
            message=message
        )
        
    def create_update_job_progress_message(self, job_id: str, worker_id: str,
                                          progress: int,
                                          status: str = "processing",
                                          message: Optional[str] = None) -> BaseMessage:
        """
        Create a job progress update message.
        
        Args:
            job_id: ID of the job
            worker_id: ID of the worker processing the job
            progress: Progress percentage (0-100)
            status: Job status (default: "processing")
            message: Optional status message
            
        Returns:
            BaseMessage: UpdateJobProgressMessage model
        """
        # Create and return a new UpdateJobProgressMessage
        # Using a different variable name to avoid confusion with the parameter
        progress_message = UpdateJobProgressMessage(
            type=MessageType.UPDATE_JOB_PROGRESS,
            job_id=job_id,
            worker_id=worker_id,
            progress=progress,
            status=status,
            message=message
        )
        return progress_message
    
    def create_worker_registered_message(self, worker_id: str, 
                                        status: str = "active") -> BaseMessage:
        """
        Create a worker registered message.
        Args:
            worker_id: ID of the registered worker
            status: Worker status
            
        Returns:
            WorkerRegisteredMessage: Worker registered message model
        """
        return WorkerRegisteredMessage(
            type=MessageType.WORKER_REGISTERED,
            worker_id=worker_id,
            status=status
        )
    
    def create_job_available_message(self, job_id: str, job_type: str,
                                    priority: Optional[int] = 0,
                                    job_request_payload: Optional[Dict[str, Any]] = None) -> BaseMessage:
        """
        Create a job available message.
        
        Args:
            job_id: ID of the available job
            job_type: Type of the job
            priority: Optional job priority
            job_request_payload: Optional job request payload
            
        Returns:
            BaseMessage: Job available message model
        """
        return JobAvailableMessage(
            type=MessageType.JOB_AVAILABLE,
            job_id=job_id,
            job_type=job_type,
            priority=priority,
            job_request_payload=job_request_payload
        )
    
    def create_job_completed_message(self, job_id: str, status: str = "completed",
                                    priority: Optional[int] = None,
                                    position: Optional[int] = None,
                                    result: Optional[Dict[str, Any]] = None) -> BaseMessage:
        """
        Create a job completed message.
        
        Args:
            job_id: ID of the completed job
            status: Job status
            priority: Optional job priority
            position: Optional position in queue
            result: Optional job result
            
        Returns:
            BaseMessage: Job completed message model
        """
        # NOTE: Now using COMPLETE_JOB instead of JOB_COMPLETED to consolidate message types
        return JobCompletedMessage(
            type=MessageType.COMPLETE_JOB,
            job_id=job_id,
            status=status,
            priority=priority,
            position=position,
            result=result
        )
    
    def validate_submit_job_message(self, data: Dict[str, Any]) -> bool:
        """
        Validate a submit job message.
        
        Args:
            data: Message data to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        if not isinstance(data, dict):
            return False
        
        required_fields = ["job_type", "payload"]
        for field in required_fields:
            if field not in data:
                return False
        
        return True
    
    def validate_get_job_status_message(self, data: Dict[str, Any]) -> bool:
        """
        Validate a get job status message.
        
        Args:
            data: Message data to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        if not isinstance(data, dict):
            return False
        
        # Check for required fields
        if "job_id" not in data:
            return False
        
        # Ensure job_id is a string
        if not isinstance(data["job_id"], str):
            return False
        
        return True
    
    def validate_register_worker_message(self, data: Dict[str, Any]) -> bool:
        """
        Validate a register worker message.
        
        Args:
            data: Message data to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        if not isinstance(data, dict):
            return False
        
        # Check for required fields
        required_fields = ["worker_id"]
        for field in required_fields:
            if field not in data:
                return False
        
        # Ensure worker_id is a string
        if not isinstance(data["worker_id"], str):
            return False
        
        return True
    
    # Renamed from create_stats_response_message to follow a consistent request-response naming pattern
    def create_response_stats_message(self, stats: Dict[str, Any]) -> ResponseStatsMessage:
        """
        Create a stats response message.
        
        Args:
            stats: System statistics
            
        Returns:
            ResponseStatsMessage: Stats response message model
        """
        return ResponseStatsMessage(
            type=MessageType.RESPONSE_STATS,
            stats=stats,
            timestamp=time.time()
        )
        
    # Keep the old method for backward compatibility
    def create_stats_response_message(self, stats: Dict[str, Any]) -> ResponseStatsMessage:
        """
        Create a stats response message (alias for create_response_stats_message).
        
        Args:
            stats: System statistics
            
        Returns:
            ResponseStatsMessage: Stats response message model
        """
        return self.create_response_stats_message(stats)
        
    def create_stats_broadcast_message(self, connections: Dict[str, List[str]],
                                      workers: Dict[str, Dict[str, Any]],
                                      subscriptions: Dict[str, Any],
                                      system: Optional[Dict[str, Any]] = None) -> StatsBroadcastMessage:
        """
        Create a stats broadcast message for monitors.
        
        Args:
            connections: Dictionary of connection lists (clients, workers, monitors)
            workers: Dictionary of worker statuses
            subscriptions: Dictionary of subscription information
            system: Optional system statistics from Redis
            
        Returns:
            StatsBroadcastMessage: Stats broadcast message model
        """
        return StatsBroadcastMessage(
            type=MessageType.STATS_BROADCAST,
            message_id=f"stats-{int(time.time())}",
            connections=connections,
            workers=workers,
            subscriptions=subscriptions,
            system=system
        )
    
    def create_unknown_message(self, content: str) -> UnknownMessage:
        """
        Create a message for unknown message types.
        
        Args:
            content: Message content
            
        Returns:
            UnknownMessage: Unknown message model
        """
        return UnknownMessage(
            type=MessageType.UNKNOWN,
            content=content,
            timestamp=time.time()
        )
    
    def create_ack_message(self, original_id: str) -> AckMessage:
        """
        Create an acknowledgment message.
        
        Args:
            original_id: ID of the original message being acknowledged
            
        Returns:
            AckMessage: Acknowledgment message model
        """
        return AckMessage(
            type=MessageType.ACK,
            message_id=f"ack-{int(time.time())}",
            original_id=original_id,
            timestamp=time.time()
        )
    
    def create_subscription_confirmed_message(self, job_id: str) -> SubscriptionConfirmedMessage:
        """
        Create a subscription confirmed message.
        
        Args:
            job_id: ID of the job being subscribed to
            
        Returns:
            BaseMessage: Subscription confirmed message model
        """
        return SubscriptionConfirmedMessage(
            type=MessageType.SUBSCRIPTION_CONFIRMED,
            job_id=job_id,
            timestamp=time.time()
        )
    
    def create_job_notifications_subscribed_message(self, worker_id: str) -> JobNotificationsSubscribedMessage:
        """
        Create a job notifications subscribed message.
        
        Returns:
            JobNotificationsSubscribedMessage: Job notifications subscribed message model
        """
        logger.debug(f"[MessageModels] Creating job notifications subscribed message for worker {worker_id}")
        return JobNotificationsSubscribedMessage(
            type=MessageType.JOB_NOTIFICATIONS_SUBSCRIBED,
            worker_id=worker_id,
            timestamp=time.time()
        )
        
    def create_job_completed_ack_message(self, job_id: str, worker_id: str) -> JobCompletedAckMessage:
        """
        Create a job completed acknowledgment message.
        
        Args:
            job_id: ID of the completed job
            worker_id: ID of the worker that completed the job
            
        Returns:
            JobCompletedAckMessage: Job completed acknowledgment message model
        """
        return JobCompletedAckMessage(
            job_id=job_id,
            worker_id=worker_id
        )

