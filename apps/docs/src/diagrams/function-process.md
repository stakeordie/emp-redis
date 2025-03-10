# Function-Level Process Flow

This document provides a detailed function-level view of how job data flows through the EMP Redis system.

## Job Submission Process

```mermaid
sequenceDiagram
    participant Client
    participant Routes as routes.py
    participant RedisService as redis_service.py
    participant Redis
    
    Client->>Routes: Submit Job Request
    Note over Routes: handle_submit_job(client_id, message_data)
    Routes->>Routes: Extract job_type, priority, payload
    Routes->>RedisService: add_job(job_id, job_type, priority, job_request_payload, client_id)
    Note over RedisService: Convert job_request_payload to JSON string
    RedisService->>Redis: hset(job_key, mapping=job_data)
    
    alt priority > 0
        RedisService->>Redis: zadd(PRIORITY_QUEUE, {job_id: priority})
    else
        RedisService->>Redis: lpush(STANDARD_QUEUE, job_id)
    end
    
    RedisService->>RedisService: notify_idle_workers_of_job(job_id, job_type, job_request_payload_json)
    RedisService->>Redis: smembers("workers:idle")
    RedisService->>Redis: publish("job_notifications", notification_json)
    RedisService-->>Routes: Return job_data
    Routes->>Client: Job Submitted Response
```

## Worker Registration Process

```mermaid
sequenceDiagram
    participant Worker
    participant Routes as routes.py
    participant RedisService as redis_service.py
    participant Redis
    
    Worker->>Routes: WebSocket Connection
    Routes->>Routes: handle_worker_connection(websocket)
    Worker->>Routes: Register Worker Message
    Routes->>Routes: handle_register_worker(worker_id, message)
    Routes->>RedisService: register_worker(worker_id, worker_type, capabilities)
    RedisService->>Redis: hset(worker_key, mapping=worker_data)
    RedisService->>Redis: sadd("workers:all", worker_id)
    RedisService->>Redis: sadd("workers:idle", worker_id)
    RedisService-->>Routes: Return worker_data
    Routes->>Worker: Registration Confirmation
```

## Job Claiming Process

```mermaid
sequenceDiagram
    participant Worker
    participant Routes as routes.py
    participant RedisService as redis_service.py
    participant Redis
    
    Worker->>Routes: Claim Job Message
    Routes->>Routes: handle_claim_job(worker_id, message)
    Routes->>RedisService: claim_job(job_id, worker_id, claim_timeout)
    
    Note over RedisService: Begin Redis Transaction
    RedisService->>Redis: hget(job_key, "status")
    
    alt status == "pending"
        RedisService->>Redis: hset(job_key, "status", "claimed")
        RedisService->>Redis: hset(job_key, "worker_id", worker_id)
        RedisService->>Redis: hset(job_key, "claimed_at", time.time())
        RedisService->>Redis: srem("workers:idle", worker_id)
        RedisService->>Redis: hset(worker_key, "status", "busy")
        RedisService->>Redis: hset(worker_key, "current_job_id", job_id)
        Note over RedisService: Execute Transaction
        RedisService->>RedisService: get_job(job_id)
        RedisService-->>Routes: Return job_data
    else
        Note over RedisService: Abort Transaction
        RedisService-->>Routes: Return None (Job unavailable)
    end
    
    Routes->>Worker: Job Claim Response
```

## Job Processing Flow

```mermaid
sequenceDiagram
    participant Worker
    participant Routes as routes.py
    participant RedisService as redis_service.py
    participant Redis
    participant Clients
    
    Worker->>Routes: Update Job Progress Message
    Routes->>Routes: handle_update_job_progress(worker_id, message)
    Routes->>RedisService: update_job_progress(job_id, progress, status_message)
    RedisService->>Redis: hset(job_key, mapping=update_data)
    RedisService->>Redis: publish("job_updates", update_json)
    
    Note over Routes: Notify subscribed clients
    Routes->>Clients: Send Job Update
    
    Worker->>Routes: Complete Job Message
    Routes->>Routes: handle_complete_job(worker_id, message)
    Routes->>RedisService: complete_job(job_id, result, error)
    
    RedisService->>Redis: hset(job_key, mapping=completion_data)
    RedisService->>Redis: sadd("workers:idle", worker_id)
    RedisService->>Redis: hset(worker_key, "status", "idle")
    RedisService->>Redis: hdel(worker_key, "current_job_id")
    
    RedisService->>Redis: publish("job_updates", completion_json)
    Routes->>Clients: Send Job Completion Update
```

## Job Retrieval Process

```mermaid
sequenceDiagram
    participant Client
    participant Routes as routes.py
    participant RedisService as redis_service.py
    participant Redis
    
    Client->>Routes: Get Job Status Request
    Routes->>Routes: handle_get_job_status(client_id, message_data)
    Routes->>RedisService: get_job(job_id)
    
    RedisService->>Redis: exists(job_key)
    RedisService->>Redis: hgetall(job_key)
    
    Note over RedisService: Process job_data
    alt "job_request_payload" in job_data
        RedisService->>RedisService: json.loads(job_data["job_request_payload"])
    else if "params" in job_data (backward compatibility)
        RedisService->>RedisService: json.loads(job_data["params"])
        RedisService->>RedisService: Rename to "job_request_payload"
    end
    
    alt "result" in job_data
        RedisService->>RedisService: json.loads(job_data["result"])
    end
    
    RedisService-->>Routes: Return job_data
    Routes->>Client: Job Status Response
```

## Worker Heartbeat Process

```mermaid
sequenceDiagram
    participant Worker
    participant Routes as routes.py
    participant RedisService as redis_service.py
    participant Redis
    
    loop Every heartbeat interval
        Worker->>Routes: Worker Heartbeat Message
        Routes->>Routes: handle_worker_heartbeat(worker_id, message)
        Routes->>RedisService: update_worker_heartbeat(worker_id)
        RedisService->>Redis: hset(worker_key, "last_heartbeat", time.time())
        RedisService-->>Routes: Heartbeat Acknowledged
        Routes->>Worker: Heartbeat Response
    end
```

## Worker Status Management

```mermaid
sequenceDiagram
    participant Worker
    participant Routes as routes.py
    participant RedisService as redis_service.py
    participant Redis
    participant Monitor
    
    Worker->>Routes: Worker Status Message
    Routes->>Routes: handle_worker_status(worker_id, message)
    Routes->>RedisService: update_worker_status(worker_id, status, metadata)
    
    alt status == "idle"
        RedisService->>Redis: sadd("workers:idle", worker_id)
    else
        RedisService->>Redis: srem("workers:idle", worker_id)
    end
    
    RedisService->>Redis: hset(worker_key, mapping=status_data)
    RedisService->>Redis: publish("worker_status", status_json)
    
    Routes->>Monitor: Send Worker Status Update
```

## Job Request Payload Data Flow

```mermaid
flowchart TD
    subgraph Client_Side
        A1[Client Request] --> A2[JSON Object]
    end
    
    subgraph Routes_Layer
        A2 --> B1[handle_submit_job]
        B1 --> B2[Extract as Dict]
    end
    
    subgraph RedisService_Layer
        B2 --> C1[add_job]
        C1 --> C2[json.dumps]
        C2 --> C3[Store in job_data]
        C3 --> C4[hset to Redis]
        
        C3 --> C5[notify_idle_workers_of_job]
        C5 --> C6[Include in notification]
    end
    
    subgraph Worker_Side
        D1[Receive Notification] --> D2[Claim Job]
        D2 --> D3[get_job]
        D3 --> D4[json.loads]
        D4 --> D5[Process Job]
    end
    
    C6 --> D1
```

## Function Call Dependencies

```mermaid
flowchart TD
    subgraph routes.py
        A1[handle_submit_job]
        A2[handle_register_worker]
        A3[handle_claim_job]
        A4[handle_update_job_progress]
        A5[handle_complete_job]
        A6[handle_worker_heartbeat]
        A7[handle_worker_status]
        A8[handle_get_job_status]
    end
    
    subgraph redis_service.py
        B1[add_job]
        B2[register_worker]
        B3[claim_job]
        B4[update_job_progress]
        B5[complete_job]
        B6[update_worker_heartbeat]
        B7[update_worker_status]
        B8[get_job]
        B9[notify_idle_workers_of_job]
        B10[check_worker_heartbeats]
    end
    
    A1 --> B1
    B1 --> B9
    A2 --> B2
    A3 --> B3
    B3 --> B8
    A4 --> B4
    A5 --> B5
    A6 --> B6
    A7 --> B7
    A8 --> B8
```

## Proposed Optimized Job Request Payload Flow

```mermaid
flowchart TD
    subgraph Current_Implementation
        A1[Client Request] --> A2[Python Dict in routes.py]
        A2 --> A3[add_job receives Dict]
        A3 --> A4[json.dumps in add_job]
        A4 --> A5[Store JSON String in Redis]
        A5 --> A6[get_job retrieves String]
        A6 --> A7[json.loads in get_job]
        A7 --> A8[Return Dict to caller]
    end
    
    subgraph Optimized_Implementation
        B1[Client Request] --> B2[Python Dict in routes.py]
        B2 --> B3[add_job accepts Dict or String]
        
        B3 -->|If Dict| B4[json.dumps in add_job]
        B3 -->|If String| B5[Validate JSON in add_job]
        
        B4 --> B6[Store JSON String in Redis]
        B5 --> B6
        
        B6 --> B7[get_job retrieves String]
        B7 --> B8[Return String to caller]
        B8 --> B9[Caller parses only when needed]
    end
```

This documentation provides a detailed view of how the different functions in the system interact, showing the complete flow of job data and control through the various components.
