# EmProps Redis Architecture

This document provides an overview of the EmProps Redis system architecture, including the interfaces, components, and their interactions.

## System Overview

The EmProps Redis system is a distributed job queue system that uses Redis as a backend. It consists of several components:

1. **Hub**: The central WebSocket server that manages connections, routes messages, and provides the client interface
2. **Worker**: A service that processes jobs from the queue
3. **Redis**: The backend storage and message broker

## Component Architecture

<FullscreenDiagram>

```mermaid
flowchart TD
    subgraph ClientApps["Client Applications"]
        Client1["Client App 1"]
        Client2["Client App 2"]
    end

    subgraph EmPropsSystem["EmProps Redis System"]
        subgraph InterfaceLayer["Interface Layer"]
            Hub["WebSocket Hub"]
        end

        subgraph WorkerLayer["Worker Layer"]
            Worker1["Worker 1"]
            Worker2["Worker 2"]
            WorkerN["Worker N"]
        end

        subgraph CoreServices["Core Services"]
            RedisService["Redis Service"]
            ConnectionManager["Connection Manager"]
            MessageHandler["Message Handler"]
            MessageModels["Message Models"]
            RouteHandler["Route Handler"]
        end

        subgraph StorageLayer["Storage Layer"]
            Redis[("Redis")]
        end
    end

    Client1 -->|"WebSocket"| Hub
    Client2 -->|"WebSocket"| Hub
    
    Hub -->|"Use"| ConnectionManager
    Hub -->|"Use"| MessageHandler
    Hub -->|"Use"| RouteHandler
    
    ConnectionManager -->|"Manage Connections"| Worker1
    ConnectionManager -->|"Manage Connections"| Worker2
    ConnectionManager -->|"Manage Connections"| WorkerN
    
    MessageHandler -->|"Parse/Validate"| MessageModels
    RouteHandler -->|"Use"| MessageHandler
    
    RedisService -->|"Store/Retrieve"| Redis
    MessageHandler -->|"Use"| RedisService

    style Hub fill:#f9f,stroke:#333,stroke-width:2px
    style RedisService fill:#bfb,stroke:#333,stroke-width:2px
    style Redis fill:#fbb,stroke:#333,stroke-width:2px
    style ConnectionManager fill:#fbf,stroke:#333,stroke-width:2px
```

</FullscreenDiagram>

## Interface Architecture

The system is built around a set of interfaces that define the contracts between components:

<FullscreenDiagram>

```mermaid
classDiagram
    class RedisServiceInterface {
        +connect_async()
        +close_async()
        +init_redis()
        +close()
        +add_job()
        +get_next_job()
        +get_job_status()
        +update_job_progress()
        +complete_job()
        +fail_job()
        +register_worker()
        +update_worker_status()
        +worker_heartbeat()
        +get_stats()
        +cleanup_stale_jobs()
        +cleanup_stale_claims()
        +mark_stale_workers_out_of_service()
    }

    class ConnectionManagerInterface {
        +connect_client()
        +connect_worker()
        +connect_monitor()
        +disconnect_client()
        +disconnect_worker()
        +disconnect_monitor()
        +send_to_client()
        +send_to_worker()
        +send_to_monitor()
        +broadcast_to_clients()
        +broadcast_to_workers()
        +broadcast_to_monitors()
        +broadcast_stats()
        +subscribe_to_job()
        +subscribe_to_stats()
        +subscribe_to_job_notifications()
        +notify_job_update()
    }

    class MessageHandlerInterface {
        +handle_message()
        +register_handler()
        +get_handler()
    }

    class MessageModelsInterface {
        +parse_message()
        +create_error_message()
        +create_job_accepted_message()
        +create_job_status_message()
        +create_worker_registered_message()
        +create_stats_response_message()
        +validate_submit_job_message()
        +validate_get_job_status_message()
        +validate_register_worker_message()
    }

    class RouteHandlerInterface {
        +init_routes()
        +client_websocket()
        +worker_websocket()
        +monitor_websocket()
        +start_background_tasks()
        +stop_background_tasks()
        +handle_client_message()
        +handle_worker_message()
        +handle_monitor_message()
    }

    class RedisService {
        +client
        +async_client
        +pubsub
        +connect_async()
        +close_async()
        +init_redis()
        +close()
        +add_job()
        +get_next_job()
        +get_job_status()
        +update_job_progress()
        +complete_job()
        +fail_job()
        +register_worker()
        +update_worker_status()
        +worker_heartbeat()
        +get_stats()
        +cleanup_stale_jobs()
        +cleanup_stale_claims()
        +mark_stale_workers_out_of_service()
    }

    class ConnectionManager {
        +client_connections
        +worker_connections
        +monitor_connections
        +job_subscriptions
        +stats_subscriptions
        +job_notification_subscriptions
        +connect_client()
        +connect_worker()
        +connect_monitor()
        +disconnect_client()
        +disconnect_worker()
        +disconnect_monitor()
        +send_to_client()
        +send_to_worker()
        +send_to_monitor()
        +broadcast_to_clients()
        +broadcast_to_workers()
        +broadcast_to_monitors()
        +broadcast_stats()
        +subscribe_to_job()
        +subscribe_to_stats()
        +subscribe_to_job_notifications()
        +notify_job_update()
    }

    RedisServiceInterface <|.. RedisService : implements
    ConnectionManagerInterface <|.. ConnectionManager : implements
    
    MessageHandlerInterface -- RedisServiceInterface : uses
    MessageHandlerInterface -- ConnectionManagerInterface : uses
    MessageHandlerInterface -- MessageModelsInterface : uses
    RouteHandlerInterface -- MessageHandlerInterface : uses
    RouteHandlerInterface -- ConnectionManagerInterface : uses
```

</FullscreenDiagram>

## Message Flow

The following diagram illustrates how messages flow through the system:

<FullscreenDiagram>

```mermaid
sequenceDiagram
    actor Client
    actor Worker1
    actor Worker2
    participant Hub
    participant ConnectionManager
    participant MessageHandler
    participant RedisService
    participant Redis

    %% Worker Registration
    Worker1->>Hub: Connect (WebSocket)
    Hub->>MessageHandler: handle_message()
    MessageHandler->>RedisService: register_worker()
    RedisService->>Redis: Store worker info
    RedisService->>Redis: Add to workers:all set
    RedisService->>Redis: Add to workers:idle set
    Hub-->>Worker1: Connection confirmed

    Worker2->>Hub: Connect (WebSocket)
    Hub->>MessageHandler: handle_message()
    MessageHandler->>RedisService: register_worker()
    RedisService->>Redis: Store worker info
    RedisService->>Redis: Add to workers:all set
    RedisService->>Redis: Add to workers:idle set
    Hub-->>Worker2: Connection confirmed

    %% Client Connection
    Client->>Hub: Connect (WebSocket)
    Hub->>ConnectionManager: connect_client()
    ConnectionManager-->>Hub: Connection established
    Hub-->>Client: Connection confirmed

    %% Job Submission
    Client->>Hub: Submit job message
    Hub->>MessageHandler: handle_message()
    MessageHandler->>RedisService: add_job()
    RedisService->>Redis: Store job data
    Redis-->>RedisService: Job stored
    RedisService->>Redis: Publish job notification
    RedisService-->>MessageHandler: Job data with position
    MessageHandler-->>Hub: Job accepted message
    Hub-->>Client: Job accepted response

    %% Job Notification
    Redis->>Hub: Job available notification
    Hub->>ConnectionManager: broadcast_to_workers()
    ConnectionManager->>Worker1: Job available message
    ConnectionManager->>Worker2: Job available message

    %% Job Claiming (race condition)
    Worker1->>Hub: Claim job request
    Worker2->>Hub: Claim job request
    Hub->>MessageHandler: handle_message()
    MessageHandler->>RedisService: claim_job()
    RedisService->>Redis: Atomic transaction
    Redis-->>RedisService: Job claimed by Worker1
    RedisService-->>MessageHandler: Job data
    MessageHandler-->>Hub: Job assigned message
    Hub-->>Worker1: Job assigned response
    Hub-->>Worker2: Job already claimed

    %% Worker Status Update
    Worker1->>Hub: Update status to busy
    Hub->>MessageHandler: handle_message()
    MessageHandler->>RedisService: update_worker_status()
    RedisService->>Redis: Remove from workers:idle
    RedisService->>Redis: Update status to busy

    %% Job Processing
    Worker1->>Hub: Update job progress
    Hub->>MessageHandler: handle_message()
    MessageHandler->>RedisService: update_job_progress()
    RedisService->>Redis: Update job status
    Redis-->>RedisService: Status updated
    RedisService->>Redis: Publish job update
    Redis->>Hub: Job update notification
    Hub->>ConnectionManager: notify_job_update()
    ConnectionManager->>Client: Job update message

    %% Job Completion
    Worker1->>Hub: Complete job
    Hub->>MessageHandler: handle_message()
    MessageHandler->>RedisService: complete_job()
    RedisService->>Redis: Mark job as completed
    Redis-->>RedisService: Job completed
    RedisService->>Redis: Publish job completion
    Redis->>Hub: Job completion notification
    Hub->>ConnectionManager: notify_job_update()
    ConnectionManager->>Client: Job completed message

    %% Worker Back to Idle
    Worker1->>Hub: Update status to idle
    Hub->>MessageHandler: handle_message()
    MessageHandler->>RedisService: update_worker_status()
    RedisService->>Redis: Add to workers:idle
    RedisService->>Redis: Update status to idle
```

</FullscreenDiagram>

## System Deployment

The system can be deployed in various configurations:

<FullscreenDiagram>

```mermaid
flowchart TD
    subgraph DevEnv["Development Environment"]
        DevClient["Client"]
        DevHub["Hub"]
        DevWorker["Worker"]
        DevRedis[("Redis")]
        
        DevClient -->|"WebSocket"| DevHub
        DevHub -->|"Store/Retrieve"| DevRedis
        DevWorker -->|"WebSocket"| DevHub
        DevWorker -->|"Process Jobs"| DevRedis
    end
    
    subgraph ProdEnv["Production Environment"]
        subgraph ClientTier["Client Tier"]
            ProdClient1["Client 1"]
            ProdClient2["Client 2"]
            ProdClientN["Client N"]
        end
        
        subgraph HubTier["Hub Tier"]
            LoadBalancer["Load Balancer"]
            ProdHub1["Hub 1"]
            ProdHub2["Hub 2"]
            ProdHubN["Hub N"]
        end
        
        subgraph WorkerTier["Worker Tier"]
            ProdWorker1["Worker 1"]
            ProdWorker2["Worker 2"]
            ProdWorkerN["Worker N"]
        end
        
        subgraph DataTier["Data Tier"]
            RedisCluster[("Redis Cluster")]
            Sentinel1["Redis Sentinel 1"]
            Sentinel2["Redis Sentinel 2"]
            Sentinel3["Redis Sentinel 3"]
        end
        
        ProdClient1 -->|"WebSocket"| LoadBalancer
        ProdClient2 -->|"WebSocket"| LoadBalancer
        ProdClientN -->|"WebSocket"| LoadBalancer
        
        LoadBalancer -->|"Route"| ProdHub1
        LoadBalancer -->|"Route"| ProdHub2
        LoadBalancer -->|"Route"| ProdHubN
        
        ProdHub1 -->|"Store/Retrieve"| RedisCluster
        ProdHub2 -->|"Store/Retrieve"| RedisCluster
        ProdHubN -->|"Store/Retrieve"| RedisCluster
        
        ProdWorker1 -->|"WebSocket"| LoadBalancer
        ProdWorker2 -->|"WebSocket"| LoadBalancer
        ProdWorkerN -->|"WebSocket"| LoadBalancer
        
        Sentinel1 -->|"Monitor"| RedisCluster
        Sentinel2 -->|"Monitor"| RedisCluster
        Sentinel3 -->|"Monitor"| RedisCluster
    end
```

</FullscreenDiagram>

## Refactoring Plan

The refactoring plan involves the following steps:

<FullscreenDiagram>

```mermaid
flowchart TD
    Start(["Start"]) --> CreateInterfaces["Create Interfaces"]
    CreateInterfaces --> UpdateRedisService["Update RedisService"]
    CreateInterfaces --> UpdateConnectionManager["Update ConnectionManager"]
    CreateInterfaces --> CreateMessageHandler["Create MessageHandler"]
    CreateInterfaces --> CreateMessageModels["Create MessageModels"]
    CreateInterfaces --> CreateRouteHandler["Create RouteHandler"]
    
    UpdateRedisService --> UpdateHub["Update Hub"]
    UpdateConnectionManager --> UpdateHub
    CreateMessageHandler --> UpdateHub
    CreateMessageModels --> UpdateHub
    CreateRouteHandler --> UpdateHub
    
    UpdateHub --> UpdateWorker["Update Worker"]
    
    UpdateWorker --> TestSystem["Test System"]
    
    TestSystem --> End(["End"])
    
    style Start fill:#f9f,stroke:#333,stroke-width:2px
    style End fill:#f9f,stroke:#333,stroke-width:2px
    style CreateInterfaces fill:#bfb,stroke:#333,stroke-width:2px
    style TestSystem fill:#fbf,stroke:#333,stroke-width:2px
```

</FullscreenDiagram>
