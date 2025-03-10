# Job Processing Flow Diagram

This document outlines the flow of job requests and data through the EMP Redis system.

## Job Request Payload Flow

```mermaid
flowchart TD
    subgraph Client
        A[Client Application] --> B[Create Job Request]
    end
    
    subgraph API
        B --> C[handle_submit_job]
        C --> D[Extract Payload as Dict]
    end
    
    subgraph RedisService
        D --> E[add_job Method]
        E --> F[Convert to JSON String]
        F --> G[Store in Redis]
        G --> H[Notify Workers]
    end
    
    subgraph Worker
        H --> I[Receive Job Notification]
        I --> J[Claim Job]
        J --> K[get_job Method]
        K --> L[Parse JSON String to Dict]
        L --> M[Process Job]
        M --> N[Complete Job]
    end
    
    subgraph Monitor
        G --> O[Monitor Job Status]
    end
```

## Job Lifecycle State Diagram

```mermaid
stateDiagram-v2
    [*] --> Pending: Job Submitted
    Pending --> Claimed: Worker Claims Job
    Claimed --> InProgress: Worker Starts Processing
    InProgress --> Completed: Job Completes Successfully
    InProgress --> Failed: Job Fails
    Claimed --> Failed: Worker Disconnects
    Pending --> Failed: Job Expires
    Completed --> [*]
    Failed --> [*]
```

## System Architecture

```mermaid
flowchart LR
    subgraph Clients
        C1[Client 1]
        C2[Client 2]
        C3[Client N]
    end
    
    subgraph API_Layer
        API[API Service]
    end
    
    subgraph Redis_Layer
        R1[Redis Service]
        R2[Redis Database]
        R1 <--> R2
    end
    
    subgraph Workers
        W1[Worker 1]
        W2[Worker 2]
        W3[Worker N]
    end
    
    subgraph Monitors
        M1[Monitor UI]
    end
    
    C1 --> API
    C2 --> API
    C3 --> API
    
    API --> R1
    
    R1 --> W1
    R1 --> W2
    R1 --> W3
    
    R1 --> M1
    
    W1 --> R1
    W2 --> R1
    W3 --> R1
```

## Data Transformation Flow

```mermaid
flowchart TD
    subgraph Client_Side
        A1[JSON Object] --> A2[HTTP Request]
    end
    
    subgraph Server_Side
        A2 --> B1[Python Dictionary]
        B1 --> B2[JSON String]
        B2 --> B3[Redis Storage]
    end
    
    subgraph Worker_Side
        B3 --> C1[JSON String]
        C1 --> C2[Python Dictionary]
        C2 --> C3[Process Job]
        C3 --> C4[Result Dictionary]
        C4 --> C5[JSON String]
    end
    
    subgraph Result_Flow
        C5 --> D1[Redis Storage]
        D1 --> D2[JSON String]
        D2 --> D3[Python Dictionary]
        D3 --> D4[Client Response]
    end
```

## Proposed Optimization

```mermaid
flowchart TD
    subgraph Current_Flow
        A1[Client Request] --> A2[Python Dict]
        A2 --> A3[JSON String]
        A3 --> A4[Redis Storage]
        A4 --> A5[JSON String]
        A5 --> A6[Python Dict]
        A6 --> A7[Worker Processing]
    end
    
    subgraph Optimized_Flow
        B1[Client Request] --> B2[Python Dict]
        B2 --> B3[JSON String]
        B3 --> B4[Redis Storage]
        B4 --> B5[JSON String]
        B5 --> B6[Worker Processing]
        
        B2 -.-> |"Skip if already string"| B3
        B5 -.-> |"Parse only when needed"| B6
    end
```

## Message Structure

```mermaid
classDiagram
    class BaseMessage {
        +str type
        +float timestamp
    }
    
    class JobAvailableMessage {
        +str job_id
        +str job_type
        +int priority
        +str job_request_payload
    }
    
    class JobUpdateMessage {
        +str job_id
        +str status
        +float progress
        +str message
    }
    
    class WorkerStatusMessage {
        +str worker_id
        +str status
        +str job_id
        +str job_type
    }
    
    BaseMessage <|-- JobAvailableMessage
    BaseMessage <|-- JobUpdateMessage
    BaseMessage <|-- WorkerStatusMessage
```

This documentation provides a comprehensive view of how job data flows through the system, from client submission to worker processing and result delivery.
