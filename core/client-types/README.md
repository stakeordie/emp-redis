# Emp-Redis Client Types

This directory contains TypeScript types and utilities for all messages exchanged between components in the Emp-Redis system. These types ensure consistency between server and client implementations and provide compile-time type checking for TypeScript clients.

## Overview

The message type system consists of:

1. **Message Type Enum**: Defines all possible message types in the system
2. **Message Interfaces**: TypeScript interfaces for each message type
3. **Type Guards**: Helper functions to safely check message types

## Using the Type Definitions

### 1. Import the types in your TypeScript code

```typescript
import { 
  MessageType, 
  Message, 
  SubmitJobMessage, 
  JobStatusMessage,
  // ... other specific message types as needed
  isMessageType
} from '../core/client-types/messages.ts';
```

### 2. Creating typed messages

When creating messages to send to the server, use the appropriate interface:

```typescript
// Example: Creating a job submission message
const submitJobMessage: SubmitJobMessage = {
  type: MessageType.SUBMIT_JOB,
  job_type: "image_processing",
  priority: 5,
  payload: {
    image_url: "https://example.com/image.jpg",
    settings: {
      resolution: "high",
      format: "png"
    }
  },
  timestamp: Date.now() / 1000 // Optional, will be added by server if omitted
};

// Send the message via WebSocket
websocket.send(JSON.stringify(submitJobMessage));
```

### 3. Handling incoming messages

When receiving messages, use the type guards to safely handle different message types:

```typescript
websocket.onmessage = (event) => {
  try {
    const message = JSON.parse(event.data) as Message;
    
    // Handle different message types
    if (isMessageType<JobStatusMessage>(message, MessageType.JOB_STATUS)) {
      // TypeScript knows this is a JobStatusMessage
      console.log(`Job ${message.job_id} status: ${message.status}`);
      if (message.progress !== undefined) {
        updateProgressBar(message.progress);
      }
    } 
    else if (isMessageType<JobCompletedMessage>(message, MessageType.JOB_COMPLETED)) {
      // TypeScript knows this is a JobCompletedMessage
      displayJobResult(message.job_id, message.result);
    }
    else if (isMessageType<ErrorMessage>(message, MessageType.ERROR)) {
      // TypeScript knows this is an ErrorMessage
      showError(message.error, message.details);
    }
  } catch (error) {
    console.error("Failed to parse message:", error);
  }
};
```

## Best Practices

### 1. Always use the MessageType enum

Instead of hardcoding string values, always use the `MessageType` enum:

```typescript
// Good
const message = { type: MessageType.SUBMIT_JOB, ... };

// Bad
const message = { type: "submit_job", ... };
```

### 2. Use type guards for safe type checking

Always use the `isMessageType` function to check message types:

```typescript
// Good
if (isMessageType<JobStatusMessage>(message, MessageType.JOB_STATUS)) {
  // Safe to access JobStatusMessage properties
}

// Bad
if (message.type === "job_status") {
  // TypeScript doesn't know this is a JobStatusMessage
}
```

### 3. Handle unknown message types

Always include a fallback for unknown message types:

```typescript
if (isMessageType<JobStatusMessage>(message, MessageType.JOB_STATUS)) {
  // Handle job status
} 
else if (isMessageType<JobCompletedMessage>(message, MessageType.JOB_COMPLETED)) {
  // Handle job completed
} 
else {
  console.warn(`Unhandled message type: ${message.type}`);
}
```

### 4. Validate messages before sending

Ensure your messages conform to the expected structure:

```typescript
function validateSubmitJobMessage(message: SubmitJobMessage): boolean {
  return (
    message.job_type !== undefined &&
    message.payload !== undefined
  );
}

const message: SubmitJobMessage = { ... };
if (validateSubmitJobMessage(message)) {
  websocket.send(JSON.stringify(message));
} else {
  console.error("Invalid message structure");
}
```

## Example: Complete Client Implementation

Here's a complete example of a client that submits a job and handles the response:

```typescript
import { 
  MessageType, 
  Message, 
  SubmitJobMessage,
  JobAcceptedMessage,
  JobStatusMessage,
  JobCompletedMessage,
  ErrorMessage,
  isMessageType
} from '../types/messages.ts';

class EmpRedisClient {
  private ws: WebSocket;
  private messageHandlers: Map<MessageType, (message: any) => void>;

  constructor(url: string) {
    this.ws = new WebSocket(url);
    this.messageHandlers = new Map();
    
    this.ws.onmessage = (event) => this.handleMessage(event);
    this.ws.onopen = () => console.log("Connected to Emp-Redis Hub");
    this.ws.onerror = (error) => console.error("WebSocket error:", error);
    this.ws.onclose = () => console.log("Disconnected from Emp-Redis Hub");
  }

  private handleMessage(event: MessageEvent) {
    try {
      const message = JSON.parse(event.data) as Message;
      const handler = this.messageHandlers.get(message.type as MessageType);
      
      if (handler) {
        handler(message);
      } else {
        console.warn(`No handler registered for message type: ${message.type}`);
      }
    } catch (error) {
      console.error("Failed to parse message:", error);
    }
  }

  public on<T extends Message>(type: MessageType, handler: (message: T) => void) {
    this.messageHandlers.set(type, handler as (message: any) => void);
    return this;
  }

  public submitJob(jobType: string, payload: Record<string, any>, priority: number = 0): string {
    const jobId = `job-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    
    const message: SubmitJobMessage = {
      type: MessageType.SUBMIT_JOB,
      job_type: jobType,
      priority: priority,
      payload: payload,
      timestamp: Date.now() / 1000
    };
    
    this.ws.send(JSON.stringify(message));
    return jobId;
  }
}

// Usage example
const client = new EmpRedisClient("ws://localhost:8001/ws/client/{client_id");

client
  .on<JobAcceptedMessage>(MessageType.JOB_ACCEPTED, (message) => {
    console.log(`Job ${message.job_id} accepted, position in queue: ${message.position}`);
  })
  .on<JobStatusMessage>(MessageType.JOB_STATUS, (message) => {
    console.log(`Job ${message.job_id} status: ${message.status}, progress: ${message.progress}%`);
  })
  .on<JobCompletedMessage>(MessageType.JOB_COMPLETED, (message) => {
    console.log(`Job ${message.job_id} completed with result:`, message.result);
  })
  .on<ErrorMessage>(MessageType.ERROR, (message) => {
    console.error(`Error: ${message.error}`, message.details);
  });

// Submit a job
const jobId = client.submitJob("image_processing", {
  image_url: "https://example.com/image.jpg",
  settings: { resolution: "high" }
}, 5);

console.log(`Submitted job with ID: ${jobId}`);
```

## Extending the Type System

If you need to add new message types:

1. Add the new message type to the `MessageType` enum in `messages.ts`
2. Create a new interface for the message
3. Add the new interface to the `Message` union type
4. Update the Python models in `core/models.py` to match

## Troubleshooting

### Common Issues

1. **"Property 'xyz' does not exist on type 'Message'"**  
   This occurs when you try to access a property without checking the message type first. Use the `isMessageType` function to narrow the type.

2. **"Type 'string' is not assignable to type 'MessageType'"**  
   Use the `MessageType` enum instead of string literals for message types.

3. **"Object literal may only specify known properties"**  
   You're trying to add properties that aren't defined in the message interface. Check the interface definition.
