/**
 * Simple Redis Monitor - JavaScript
 * 
 * This file contains the logic for connecting to Redis via WebSocket and monitoring workers, clients, and jobs.
 * Written in plain JavaScript as per the Types Philosophy:
 * - Write in plain JavaScript first
 * - Add types after functionality works
 */

// State management
const state = {
    // Connection state
    monitorConnected: false,
    clientConnected: false,
    
    // [2025-04-06 19:02] Removed worker connection state
    
    // Redis entities
    workers: {},
    clients: {},
    jobs: {},
    
    // [2025-05-20T11:26:44-04:00] Added REST API configuration
    // [2025-05-20T11:34:47-04:00] Updated with synchronous option
    restApi: {
        url: 'http://localhost:8001/api/jobs',
        enabled: true,
        synchronous: false,  // Whether to wait for job completion
        timeout: 300        // Maximum time to wait (seconds) for synchronous requests
    },
    
    // Statistics
    stats: {
        totalWorkers: 0,
        totalClients: 0,
        activeJobs: 0,
        completedJobs: 0,
        failedJobs: 0
    },
    
    // WebSocket connections
    monitorSocket: null,  // For monitoring (receives system updates)
    clientSocket: null,   // For job submission
    
    // Pending requests tracking
    pendingRequests: {}
};

// Connection URLs
const CONNECTION_URLS = {
    railway: "wss://redisserver-production.up.railway.app",
    railwaynew: "wss://redisservernew-production.up.railway.app",
    local: "ws://localhost:8001"
};

// [2025-05-19T17:53:00-04:00] Default payloads for different job types
const DEFAULT_PAYLOADS = {
    // Simulation job type (default)
    "simulation": JSON.stringify({
        "steps": 20,
        "seed": Math.floor(Math.random() * 1000000000),
        "simulation_time": 5
    }, null, 2),
    
    // ComfyUI job type
    "comfyui": JSON.stringify({
        "3": {
          "inputs": {
            "seed": 1057618124930620,
            "steps": 20,
            "cfg": 8,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": 1,
            "model": [
              "4",
              0
            ],
            "positive": [
              "6",
              0
            ],
            "negative": [
              "7",
              0
            ],
            "latent_image": [
              "5",
              0
            ]
          },
          "class_type": "KSampler",
          "_meta": {
            "title": "KSampler"
          }
        },
        "4": {
          "inputs": {
            "ckpt_name": "sd_xl_base_1.0_0.9vae.safetensors"
          },
          "class_type": "CheckpointLoaderSimple",
          "_meta": {
            "title": "Load Checkpoint"
          }
        },
        "5": {
          "inputs": {
            "width": 1024,
            "height": 1024,
            "batch_size": 1
          },
          "class_type": "EmptyLatentImage",
          "_meta": {
            "title": "Empty Latent Image"
          }
        },
        "6": {
          "inputs": {
            "text": "dog and sdeal",
            "clip": [
              "4",
              1
            ]
          },
          "class_type": "CLIPTextEncode",
          "_meta": {
            "title": "CLIP Text Encode (Prompt)"
          }
        },
        "7": {
          "inputs": {
            "text": "text, watermark",
            "clip": [
              "4",
              1
            ]
          },
          "class_type": "CLIPTextEncode",
          "_meta": {
            "title": "CLIP Text Encode (Prompt)"
          }
        },
        "8": {
          "inputs": {
            "samples": [
              "3",
              0
            ],
            "vae": [
              "4",
              2
            ]
          },
          "class_type": "VAEDecode",
          "_meta": {
            "title": "VAE Decode"
          }
        },
        "9": {
          "inputs": {
            "filename_prefix": "ComfyUI",
            "images": [
              "8",
              0
            ]
          },
          "class_type": "SaveImage",
          "_meta": {
            "title": "Save Image"
          }
        }
      }, null, 2),
    
    // A1111 job type
    // [2025-05-19T20:45:00-04:00] Updated a1111 payload format to match connector expectations
    // [2025-05-19T20:48:00-04:00] Updated a1111 payload to include model selection
    "a1111": JSON.stringify({
        "endpoint": "txt2img",
        "method": "POST",
        "payload": {
            "prompt": "a photo of a cat",
            "negative_prompt": "blurry, bad quality",
            "width": 1024,
            "height": 1024,
            "steps": 20,
            "cfg_scale": 7,
            "sampler_name": "Euler a",
            "sampler_index": "Euler a",
            "seed": -1,
            "batch_size": 1,
            "n_iter": 1,
            "override_settings": {
                "sd_model_checkpoint": "sd_xl_base_1.0_0.9vae.safetensors"
            },
            "override_settings_restore_afterwards": true,
            "send_images": true,
            "save_images": false
        }
    }, null, 2),
    
    // REST API job type
    "rest": JSON.stringify({
        "endpoint": "/api/generate",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json"
        },
        "body": {
            "prompt": "Example prompt",
            "parameters": {
                "temperature": 0.7
            }
        }
    }, null, 2)
};

// DOM Elements
const elements = {
    // Connection controls
    connectionType: document.getElementById('connection-type'),
    websocketUrl: document.getElementById('websocket-url'),
    // [2025-05-24T12:33:00-04:00] Using jobType consistently instead of jobTypeDropdown
    // [2025-05-19T17:50:00-04:00] Added job type dropdown reference
    // [2025-05-19T17:54:00-04:00] Added job payload textarea reference
    // [2025-05-24T12:38:00-04:00] Note: This element is also referenced in the job submission section
    jobPayload: document.getElementById('job-payload'),
    authToken: document.getElementById('auth-token'),
    // Connection info display elements
    connectionInfo: document.getElementById('connection-info'),
    monitorIdDisplay: document.getElementById('monitor-id-display'),
    clientIdDisplay: document.getElementById('client-id-display'),
    workerIdDisplay: document.getElementById('worker-id-display'),
    connectBtn: document.getElementById('connect-btn'),
    disconnectBtn: document.getElementById('disconnect-btn'),
    statusIndicator: document.getElementById('status-indicator'),
    connectionStatusText: document.getElementById('connection-status-text'),
    
    // [2025-04-06 19:02] Worker simulation controls removed
    
    // Job submission
    jobType: document.getElementById('job-type'),
    jobPriority: document.getElementById('job-priority'),
    priorityButtons: document.querySelectorAll('.priority-btn'),
    // [2025-05-24T12:41:00-04:00] This is a duplicate of the jobPayload element defined in the connection controls sectio
    submitJobBtn: document.getElementById('submit-job-btn'),
    // [2025-05-20T11:26:44-04:00] Added REST API elements
    submitJobRestBtn: document.getElementById('submit-job-rest-btn'),
    restResponseContainer: document.getElementById('rest-response-container'),
    restResponse: document.getElementById('rest-response'),
    // [2025-05-20T11:30:59-04:00] Added REST API URL display element
    restApiUrl: document.getElementById('rest-api-url'),
    
    // [2025-05-24T12:50:00-04:00] Added REST API response modal elements
    restResponseModal: document.getElementById('rest-response-modal'),
    restResponseModalContent: document.getElementById('rest-response-modal-content'),
    restResponseModalClose: document.getElementById('rest-response-modal-close'),
    restResponseModalCopy: document.getElementById('rest-response-modal-copy'),
  
    // [2025-05-24T13:45:00-04:00] Added service request elements
    serviceRequestsContainer: document.getElementById('service-requests-container'),
    serviceRequestsList: document.getElementById('service-requests-list'),
    noServiceRequestsMessage: document.getElementById('no-service-requests-message'),
    // [2025-05-20T11:34:47-04:00] Added synchronous option elements
    restSyncCheckbox: document.getElementById('rest-sync-checkbox'),
    restTimeout: document.getElementById('rest-timeout'),
    // [2025-05-20T11:40:07-04:00] Added job status check elements
    jobStatusId: document.getElementById('job-status-id'),
    checkJobStatusBtn: document.getElementById('check-job-status-btn'),
    
    // Stats
    requestStatsBtn: document.getElementById('request-stats-btn'),
    workersCount: document.getElementById('workers-count'),
    clientsCount: document.getElementById('clients-count'),
    queuedJobsCount: document.getElementById('queued-jobs-count'),
    activeJobsCount: document.getElementById('active-jobs-count'),
    jobHistoryLink: document.getElementById('job-history-link'),
    
    // Tables and Containers
    // [2025-04-06 19:05] Updated worker references for card-based layout
    workersContainer: document.getElementById('workers-container'),
    jobsTableBody: document.getElementById('jobs-table-body'),
    noWorkersMessage: document.getElementById('no-workers-message'),
    noJobsMessage: document.getElementById('no-jobs-message'),
    jobsTableContainer: document.getElementById('jobs-table-container'),
    // [2025-04-06 19:40] Added finished jobs elements
    finishedJobsTableBody: document.getElementById('finished-jobs-table-body'),
    noFinishedJobsMessage: document.getElementById('no-finished-jobs-message'),
    finishedJobsContainer: document.getElementById('finished-jobs-container'),
    
    // Logs
    logs: document.getElementById('logs'),
    
    // [2025-05-24T12:45:00-04:00] Added modal elements for better organization
    jobDetailsModal: document.getElementById('job-details-modal'),
    jobDetailsContent: document.getElementById('job-details-content')
};

/**
 * Update WebSocket URL based on connection type
 * [2025-05-20T11:30:59-04:00] Also updates the REST API URL to match the WebSocket base URL
 */
function updateWebSocketUrl() {
    const connectionType = elements.connectionType.value;
    elements.websocketUrl.value = CONNECTION_URLS[connectionType];
    
    // [2025-05-20T11:30:59-04:00] Update REST API URL to match the WebSocket base URL
    updateRestApiUrl(CONNECTION_URLS[connectionType]);
    
    // If we're already connected, show a warning about changing connection
    if (state.monitorConnected) {
        addLogEntry('Connection change detected. Disconnect and reconnect to apply changes.', 'warning');
    }
}

/**
 * [2025-05-20T11:30:59-04:00] Update REST API URL based on WebSocket URL
 * @param {string} websocketUrl - The WebSocket URL to derive the REST API URL from
 */
function updateRestApiUrl(websocketUrl) {
    // Extract the base URL from the WebSocket URL
    let baseUrl = websocketUrl;
    
    // Remove any protocol prefix
    baseUrl = baseUrl.replace(/^(wss?:\/\/)/, '');
    
    // Remove any path after the domain
    baseUrl = baseUrl.split('/')[0];
    
    // Set the REST API URL
    if (baseUrl === 'localhost:8001') {
        // For local development
        state.restApi.url = 'http://localhost:8001/api/jobs';
    } else {
        // For production (Railway)
        state.restApi.url = `https://${baseUrl}/api/jobs`;
    }
    
    // Update the REST API URL display in the UI
    if (elements.restApiUrl) {
        elements.restApiUrl.textContent = state.restApi.url;
    }
    
    console.log(`[2025-05-20T11:30:59-04:00] REST API URL updated to: ${state.restApi.url}`);
}

/**
 * Generate a UUID v4
 * @returns {string} A random UUID
 */
function generateUUID() {
    // 2025-04-09 13:35: Added UUID generation for message_id uniqueness
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

/**
 * Initialize the application
 */
function init() {
    // Add event listeners
    elements.connectBtn.addEventListener('click', connect);
    elements.disconnectBtn.addEventListener('click', disconnect);
    // 2025-04-09 15:02: Fix event handling to prevent passing the event object to submitJob
    elements.submitJobBtn.addEventListener('click', (event) => {
        event.preventDefault();
        submitJob(null);
    });
    // [2025-05-20T11:26:44-04:00] Add event listener for REST API submission
    elements.submitJobRestBtn.addEventListener('click', (event) => {
        event.preventDefault();
        submitJobViaRest();
    });
    
    // [2025-05-20T11:34:47-04:00] Add event listeners for synchronous option
    if (elements.restSyncCheckbox) {
        elements.restSyncCheckbox.addEventListener('change', (event) => {
            state.restApi.synchronous = event.target.checked;
            console.log(`[2025-05-20T11:34:47-04:00] REST API synchronous mode: ${state.restApi.synchronous}`);
            
            // Update button text based on synchronous mode
            if (state.restApi.synchronous) {
                elements.submitJobRestBtn.textContent = 'Submit Job: REST (Sync)';
            } else {
                elements.submitJobRestBtn.textContent = 'Submit Job: REST';
            }
        });
    }
    
    // [2025-05-20T11:34:47-04:00] Add event listener for timeout input
    if (elements.restTimeout) {
        elements.restTimeout.addEventListener('change', (event) => {
            const timeout = parseInt(event.target.value, 10);
            if (!isNaN(timeout) && timeout > 0) {
                state.restApi.timeout = timeout;
                console.log(`[2025-05-20T11:34:47-04:00] REST API timeout: ${state.restApi.timeout} seconds`);
            } else {
                // Reset to default if invalid
                event.target.value = state.restApi.timeout;
            }
        });
    }
    
    // [2025-05-20T11:40:07-04:00] Add event listener for check job status button
    if (elements.checkJobStatusBtn) {
        elements.checkJobStatusBtn.addEventListener('click', async (event) => {
            event.preventDefault();
            await checkJobStatusFromUI();
        });
    }
    // 2025-04-09 13:41: Added batch submit button event listener
    document.getElementById('batch-submit-btn')?.addEventListener('click', batchSubmitJobs);
    elements.connectionType.addEventListener('change', updateWebSocketUrl);
    // [2025-05-24T12:33:30-04:00] Changed from jobTypeDropdown to jobType for consistency
    elements.jobType.addEventListener('change', (event) => {
        const selectedJobType = event.target.value;
        updateJobPayload(selectedJobType);
    });
    
    // Initialize WebSocket URL based on default connection type
    updateWebSocketUrl();
    
    // [2025-05-19T17:56:00-04:00] Initialize job payload with default for selected job type
    // [2025-05-24T12:34:00-04:00] Changed from jobTypeDropdown to jobType for consistency
    if (elements.jobType && elements.jobPayload) {
        const initialJobType = elements.jobType.value || 'simulation';
        updateJobPayload(initialJobType);
    }
    
    // [2025-04-06 19:02] Worker subscription event listeners removed
    
    // Set up priority buttons
    elements.priorityButtons.forEach(button => {
        button.addEventListener('click', function() {
            // Remove active class from all buttons
            elements.priorityButtons.forEach(btn => btn.classList.remove('active'));
            
            // Add active class to clicked button
            this.classList.add('active');
            
            // Update hidden input value
            elements.jobPriority.value = this.getAttribute('data-priority');
        });
    });
    
    // Set default priority button (Priority 5)
    const defaultPriorityBtn = document.querySelector('.priority-btn[data-priority="5"]');
    if (defaultPriorityBtn) {
        defaultPriorityBtn.classList.add('active');
    }
    
    // Log initialization
    addLogEntry('Application initialized', 'info');
    
    // Update UI
    updateUI();
}

/**
 * Set up event listeners for the application
 */
function setupEventListeners() {
    // Submit job form
    const submitJobForm = document.getElementById('submit-job-form');
    if (submitJobForm) {
        submitJobForm.addEventListener('submit', function(event) {
            event.preventDefault();
            submitJob();
        });
    }
    
    // [2025-04-06 19:13] Add global event listener for job action buttons
    document.addEventListener('click', function(event) {
        // Handle retry button clicks
        if (event.target.classList.contains('retry-btn')) {
            const jobId = event.target.getAttribute('data-job-id');
            if (jobId) {
                retryJob(jobId);
            }
        }
        
        // Handle details button clicks
        if (event.target.classList.contains('details-btn')) {
            const jobId = event.target.getAttribute('data-job-id');
            if (jobId) {
                showJobDetails(jobId);
            }
        }
    });
}

/**
 * Connect to Redis via WebSocket with monitor and client connections
 * Uses timestamp-based IDs for each connection type
 * [2025-04-06 20:46] Restored client connection for job submission
 */
function connect() {
    // Get base URL from form
    const baseUrl = elements.websocketUrl.value || 'wss://redisserver-production.up.railway.app';
    console.log('Base URL:', baseUrl);
    
    // Get auth token if provided
    const authToken = elements.authToken ? elements.authToken.value : '3u8sdj5389fj3kljsf90u';
    console.log('Using auth token:', authToken);
    
    // Generate timestamp for unique IDs
    const timestamp = Date.now();
    
    // [2025-04-06 19:02] Create IDs with the specified format using timestamps
    // Worker ID removed as worker simulation has been removed
    const clientId = `client-id-${timestamp}`;
    const monitorId = `monitor-id-${timestamp}`;
    
    // Store IDs in state for reference
    state.clientId = clientId;
    state.monitorId = monitorId;
    
    // Show connection info display
    if (elements.connectionInfo) {
        elements.connectionInfo.style.display = 'flex';
    }
    
    // Connection displays now show fixed 'Connected' status instead of IDs
    // The HTML has been updated to show this by default
    
    // Log connection attempt with IDs
    addLogEntry(`Initializing connections with timestamp-based IDs (${new Date(timestamp).toLocaleTimeString()})`, 'info');
    
    // Connect monitor socket
    connectMonitorSocket(baseUrl, monitorId, authToken);
    
    // Connect client socket
    connectClientSocket(baseUrl, clientId, authToken);
    
    // [2025-04-06 19:02] Worker socket connection removed
}

/**
 * Connect the monitor socket for receiving system updates
 * @param {string} baseUrl - Base WebSocket URL
 * @param {string} monitorId - Monitor connection ID
 * @param {string} authToken - Authentication token
 */
function connectMonitorSocket(baseUrl, monitorId, authToken) {
    // 2025-04-17-20:50 - Updated to handle both railway and railwaynew connection types
    const connectionType = elements.connectionType.value;
    const isProduction = connectionType === 'railway' || connectionType === 'railwaynew';
    const protocol = isProduction ? 'wss' : 'ws';
    
    // Extract host and port from baseUrl
    let host = baseUrl;
    // Remove any protocol prefix
    host = host.replace(/^(https?:\/\/|wss?:\/\/)/, '');
    
    // Format the WebSocket URL with the monitor path
    const base_url = `${protocol}://${host}/ws/monitor/${monitorId}`;
    
    // Add authentication token if provided
    const monitorUrl = authToken ? `${base_url}?token=${encodeURIComponent(authToken)}` : base_url;
    
    // Log the URL we're connecting to
    console.log('Monitor URL:', monitorUrl);
    
    addLogEntry(`Connecting monitor socket as '${monitorId}'...`, 'info');
    
    try {
        // Create monitor WebSocket connection
        state.monitorSocket = new WebSocket(monitorUrl);
        
        // Connection opened
        state.monitorSocket.addEventListener('open', (event) => {
            state.monitorConnected = true;
            addLogEntry(`Monitor connection established as '${monitorId}'`, 'success');
            
            // [2025-05-20T11:30:59-04:00] Update REST API URL based on the connected WebSocket URL
            updateRestApiUrl(monitorUrl);
            
            updateConnectionUI();
            
            // Request initial stats
            requestStats();
        });
        
        // Listen for messages
        state.monitorSocket.addEventListener('message', handleMonitorMessage);
        
        // Listen for errors - 2025-04-17-20:52 - Enhanced error logging
        state.monitorSocket.addEventListener('error', (event) => {
            console.error('Monitor socket error details:', event);
            addLogEntry(`Monitor socket error: ${event}`, 'error');
            // Try to get more details about the error
            addLogEntry(`Connection to ${monitorUrl} failed. Please check if the server is running and accessible.`, 'error');
            handleDisconnect();
        });
        
        // Listen for connection close
        state.monitorSocket.addEventListener('close', (event) => {
            addLogEntry(`Monitor socket closed: ${event.reason}`, 'warning');
            handleDisconnect();
        });
        
    } catch (error) {
        addLogEntry(`Error creating monitor socket: ${error}`, 'error');
        handleDisconnect();
    }
}

/**
 * Connect the client socket for job submission
 * @param {string} baseUrl - Base WebSocket URL
 * @param {string} clientId - Client connection ID
 * @param {string} authToken - Authentication token
 */
function connectClientSocket(baseUrl, clientId, authToken) {
    // 2025-04-17-20:50 - Updated to handle both railway and railwaynew connection types
    const connectionType = elements.connectionType.value;
    const isProduction = connectionType === 'railway' || connectionType === 'railwaynew';
    const protocol = isProduction ? 'wss' : 'ws';
    
    // Extract host and port from baseUrl
    let host = baseUrl;
    // Remove any protocol prefix
    host = host.replace(/^(https?:\/\/|wss?:\/\/)/, '');
    
    // Format the WebSocket URL with the client path
    const base_url = `${protocol}://${host}/ws/client/${clientId}`;
    
    // Add authentication token if provided
    const clientUrl = authToken ? `${base_url}?token=${encodeURIComponent(authToken)}` : base_url;
    
    // Log the URL we're connecting to
    console.log('Client URL:', clientUrl);
    
    addLogEntry(`Connecting client socket as '${clientId}'...`, 'info');
    
    try {
        // Create client WebSocket connection
        state.clientSocket = new WebSocket(clientUrl);
        
        // Connection opened
        state.clientSocket.addEventListener('open', (event) => {
            state.clientConnected = true;
            addLogEntry(`Client connection established as '${clientId}'`, 'success');
            updateConnectionUI();
        });
        
        // Listen for messages
        state.clientSocket.addEventListener('message', handleClientMessage);
        
        // Listen for errors - 2025-04-17-20:52 - Enhanced error logging
        state.clientSocket.addEventListener('error', (event) => {
            console.error('Client socket error details:', event);
            addLogEntry(`Client socket error: ${event}`, 'error');
            // Try to get more details about the error
            addLogEntry(`Connection to ${clientUrl} failed. Please check if the server is running and accessible.`, 'error');
            handleDisconnect();
        });
        
        // Listen for connection close
        state.clientSocket.addEventListener('close', (event) => {
            addLogEntry(`Client socket closed: ${event.reason}`, 'warning');
            handleDisconnect();
        });
        
    } catch (error) {
        addLogEntry(`Error creating client socket: ${error}`, 'error');
        handleDisconnect();
    }
}

/**
 * Update the connection UI based on connection states
 * [2025-04-06 18:53] Simplified to focus on monitor and client connections
 * [2025-04-06 19:21] Fixed ReferenceError by initializing statusDetails array
 * [2025-04-06 20:46] Restored client connection handling
 */
function updateConnectionUI() {
    // Update connect/disconnect buttons
    elements.connectBtn.disabled = state.monitorConnected || state.clientConnected;
    elements.disconnectBtn.disabled = !state.monitorConnected && !state.clientConnected;
    
    // Initialize statusDetails array
    const statusDetails = [];
    
    // Update monitor connection status
    if (state.monitorConnected) {
        // Monitor connected
        const monitorId = state.monitorId || 'unknown';
        statusDetails.push(`Monitor: Connected (${monitorId})`);
        
        // Update monitor ID display if available
        if (elements.monitorIdDisplay) {
            elements.monitorIdDisplay.textContent = monitorId;
        }
    } else {
        statusDetails.push('Monitor: Disconnected');
        
        // Reset monitor ID display if available
        if (elements.monitorIdDisplay) {
            elements.monitorIdDisplay.textContent = 'Not connected';
        }
    }
    
    // Update client connection status
    if (state.clientConnected) {
        // Client connected
        const clientId = state.clientId || 'unknown';
        statusDetails.push(`Client: Connected (${clientId})`);
        
        // Update client ID display if available
        if (elements.clientIdDisplay) {
            elements.clientIdDisplay.textContent = clientId;
        }
    } else {
        statusDetails.push('Client: Disconnected');
        
        // Reset client ID display if available
        if (elements.clientIdDisplay) {
            elements.clientIdDisplay.textContent = 'Not connected';
        }
    }
    
    // Update connection status indicator with null checks
    if (elements.statusIndicator) {
        // Determine connection state
        const allConnected = state.monitorConnected && state.clientConnected;
        const anyConnected = state.monitorConnected || state.clientConnected;
        
        if (allConnected) {
            // All connections active
            elements.statusIndicator.className = 'status-indicator status-connected';
            elements.connectionStatusText.textContent = 'Connected';
            elements.connectionStatusText.style.color = '#4CAF50';
        } else if (anyConnected) {
            // At least one connection active - partial connection state
            elements.statusIndicator.className = 'status-indicator status-partial';
            elements.connectionStatusText.textContent = 'Partially Connected';
            elements.connectionStatusText.style.color = '#FF9800';
        } else {
            // No connections active
            elements.statusIndicator.className = 'status-indicator status-disconnected';
            elements.connectionStatusText.textContent = 'Disconnected';
            elements.connectionStatusText.style.color = '#F44336';
        }
    }
    
    // Update status details display if it exists
    if (elements.connectionStatusDetails) {
        elements.connectionStatusDetails.innerHTML = statusDetails.join('<br>');
    }
    
    // Add CSS for partial connection state if it doesn't exist
    if (!document.querySelector('style#connection-styles')) {
        const style = document.createElement('style');
        style.id = 'connection-styles';
        style.textContent = `
            .status-partial {
                background-color: #ff9800; /* Orange for partial connection */
            }
        `;
        document.head.appendChild(style);
    }
}

/**
 * Disconnect from WebSocket connections
 * [2025-04-06 20:46] Updated to close both monitor and client connections
 */
function disconnect() {
    addLogEntry('Disconnecting from WebSocket connections...', 'info');
    
    // Close monitor socket if it exists
    if (state.monitorSocket) {
        state.monitorSocket.close();
    }
    
    // Close client socket if it exists
    if (state.clientSocket) {
        state.clientSocket.close();
    }
    
    // Call handleDisconnect to reset state and update UI
    handleDisconnect();
}

/**
 * Handle disconnection (either manual or due to error)
 * Resets connection states and UI elements
 * [2025-04-06 20:46] Updated to properly handle both monitor and client connections
 */
function handleDisconnect() {
    // Reset connection states
    state.monitorConnected = false;
    state.clientConnected = false;
    
    // Reset socket references
    state.monitorSocket = null;
    state.clientSocket = null;
    
    // Reset connection info display
    if (elements.connectionInfo) {
        elements.connectionInfo.style.display = 'none';
    }
    
    // Reset connection ID displays
    if (elements.monitorIdDisplay) {
        elements.monitorIdDisplay.textContent = 'Not connected';
    }
    
    if (elements.clientIdDisplay) {
        elements.clientIdDisplay.textContent = 'Not connected';
    }
    
    // Enable/disable buttons based on connection status
    updateConnectionUI();
    
    // Clear data
    state.workers = {};
    state.clients = {};
    state.jobs = {};
    state.stats = {
        totalWorkers: 0,
        totalClients: 0,
        activeJobs: 0,
        failedJobs: 0
    };
    
    // Update UI
    updateUI();
    
    addLogEntry('All connections closed and data cleared', 'info');
}

/**
 * Handle incoming messages from the monitor socket
 * @param {MessageEvent} event - WebSocket message event
 */
function handleMonitorMessage(event) {
    processMessage(event.data, 'monitor');
}

/**
 * Handle incoming messages from the client socket
 * @param {MessageEvent} event - WebSocket message event
 */
function handleClientMessage(event) {
    // Process the message
    processMessage(event.data, 'client');
}

/**
 * Process WebSocket messages from any connection
 * @param {string} data - Raw message data
 * @param {string} source - Source of the message ('monitor' or 'client')
 * [2025-04-06 19:02] Removed worker as a source since worker simulation has been removed
 * [2025-04-06 19:26] Added more detailed message logging to diagnose inconsistent updates
 * [2025-04-06 20:15] Fixed syntax errors and removed duplicate code
 */
function processMessage(data, source) {
    try {
        // Parse the message data
        const message = JSON.parse(data);
        
        // Enhanced logging with timestamp and message details
        const timestamp = new Date().toISOString().substring(11, 19); // HH:MM:SS
        console.log(`[${timestamp}] ${source} message: ${message.type}`, message);
        
        // Log received message with source
        addLogEntry(`Received ${source} message: ${message.type}`, 'info');
        console.log(`Received ${source} message: ${message.type}`)
        try {
            console.log("the messagetype is: ", message.type)
            // Process the message based on its type
            // [2025-05-20T11:23:31-04:00] Removed cases for unsupported message types
            switch (message.type) {
                case Messages.TYPE.RESPONSE_STATS:
                    handleStatsResponse(message, message, source);
                    break;
                case Messages.TYPE.JOB_ACCEPTED:
                    handleJobAccepted(message, source);
                    break;
                case Messages.TYPE.UPDATE_JOB_PROGRESS:
                    handleJobProgress(message, source);
                    break;
                case Messages.TYPE.COMPLETE_JOB:
                    handleJobCompleted(message, source);
                    break;
                case Messages.TYPE.FAIL_JOB:
                    handleJobFailed(message, message, source);
                    break;
                // [2025-04-06 19:40] Added case for job cancellation
                case 'job_cancelled':
                case 'job.cancelled':
                    handleJobCancelled(message, message, source);
                    break;
                case Messages.TYPE.WORKER_REGISTERED:
                    handleWorkerRegistered(message, message, source);
                    break;
                case Messages.TYPE.WORKER_STATUS:
                    handleWorkerStatus(message, source);
                    break;
                case Messages.TYPE.ERROR:
                    handleErrorMessage(message, source);
                    break;
                case Messages.TYPE.CONNECTION_ESTABLISHED:
                    addLogEntry(`${source.charAt(0).toUpperCase() + source.slice(1)} connection established: ${message.message}`, 'success');
                    break;
                case Messages.TYPE.STATS_BROADCAST:
                    handleStatsBroadcast(message, message, source);
                    break;
                case Messages.TYPE.ACK:
                    handleAckMessage(message, message, source);
                    break;
                case 'subscribe_job_notifications':
                    // Worker is trying to subscribe to job notifications
                    if (source === 'worker') {
                        const action = message.enabled ? 'subscribe to' : 'unsubscribe from';
                        addLogEntry(`Worker ${message.worker_id} requesting to ${action} job notifications`, 'info');
                    }
                    break;
                case 'job_notifications_subscribed':
                    // Worker successfully subscribed to job notifications
                    if (source === 'worker') {
                        state.workerSubscribed = true;
                        addLogEntry(`Worker ${message.worker_id} subscribed to job notifications`, 'success');
                        
                        // Update subscription status
                        if (elements.subscriptionStatus) {
                            elements.subscriptionStatus.textContent = 'Subscribed';
                        }
                        
                        // Update button states
                        if (elements.subscribeBtn) {
                            elements.subscribeBtn.disabled = true;
                        }
                        if (elements.unsubscribeBtn) {
                            elements.unsubscribeBtn.disabled = false;
                        }
                        
                        // Update connection UI
                        updateConnectionUI();
                    }
                    break;
                case 'job_notifications_unsubscribed':
                    // Worker successfully unsubscribed from job notifications
                    if (source === 'worker') {
                        state.workerSubscribed = false;
                        addLogEntry(`Worker ${message.worker_id} unsubscribed from job notifications`, 'info');
                        
                        // Update subscription status
                        if (elements.subscriptionStatus) {
                            elements.subscriptionStatus.textContent = 'Not Subscribed';
                        }
                        
                        // Update button states
                        if (elements.subscribeBtn) {
                            elements.subscribeBtn.disabled = false;
                        }
                        if (elements.unsubscribeBtn) {
                            elements.unsubscribeBtn.disabled = true;
                        }
                        
                        // Update connection UI
                        updateConnectionUI();
                    }
                    break;
                    
                // [2025-05-24T13:45:00-04:00] Added support for service request messages
                case 'service_request':
                    // Handle service request messages from workers
                    handleServiceRequest(message, source);
                    break;
                case 'job_notification':
                    // Worker received a job notification
                    if (source === 'worker') {
                        addLogEntry(`Worker received job notification for job: ${message.job_id}`, 'info');
                    }
                    break;
                default:
                    // Log unknown message types with more detail
                    addLogEntry(`Received unhandled ${source} message type: ${message.type}`, 'warning');
                    // Store unhandled message types for debugging
                    if (!state.unhandledMessageTypes) {
                        state.unhandledMessageTypes = {};
                    }
                    if (!state.unhandledMessageTypes[message.type]) {
                        state.unhandledMessageTypes[message.type] = [];
                    }
                    // Store up to 5 examples of each unhandled type
                    if (state.unhandledMessageTypes[message.type].length < 5) {
                        state.unhandledMessageTypes[message.type].push({
                            ...message,
                            _source: source,
                            _receivedAt: new Date().toISOString()
                        });
                    }
            }
        } catch (parseError) {
            // If parsing fails, fall back to using the raw message
            addLogEntry(`Error parsing ${source} message structure: ${parseError.message}`, 'warning');
            console.warn(`${source} message parsing error:`, parseError, 'Raw message:', message);
            
            // Handle the message using the raw format as fallback
            handleRawMessage(message, source);
        }
        
        // Update UI after processing the message
        updateUI();
    } catch (error) {
        addLogEntry(`Error parsing ${source} JSON: ${error.message}`, 'error');
        console.error(`${source} JSON parsing error:`, error, data);
    }
}

/**
 * Fallback handler for raw messages when parsing fails
 * @param {Object} message - Raw message object
 * @param {string} source - Source of the message ('monitor' or 'client')
 */
function handleRawMessage(message, source = 'unknown') {
    // Simple fallback handling based on raw message type
    switch (message.type) {
        case 'response_stats':
        case 'stats_response':
            handleStatsResponse(null, message);
            break;
        case 'job_accepted':
            handleJobAccepted({ jobId: message.job_id, status: message.status });
            break;
        case 'stats_broadcast':
            handleStatsBroadcast(null, message);
            break;
        // Add other cases as needed
        default:
            console.log('Handling raw message:', message);
    }
}

/**
 * Update stats in the application state and refresh UI
 * @param {Object} statsData - Stats data received from server
 */
function updateStats(statsData) {
    try {
        console.log("[2025-04-06 18:47] Updating stats from server", statsData);
        // Extract stats from the response
        const queues = statsData.queues || {};
        const jobs = statsData.jobs || {};
        const workers = statsData.workers || {};
        
        // Update state with the new stats
        state.stats.totalWorkers = workers.total || 0;
        state.stats.totalClients = (statsData.connections && statsData.connections.clients) || 0;
        
        // Store raw job status counts from server (we'll calculate actual display counts in updateUI)
        state.stats.rawActiveJobs = (jobs.status && jobs.status.active) || 0;
        state.stats.rawPendingJobs = (jobs.status && jobs.status.pending) || 0;
        state.stats.rawFailedJobs = (jobs.status && jobs.status.failed) || 0;
        
        // Log raw job counts from server for debugging
        console.log('[2025-04-06 18:47] Raw job counts from server:', {
            queued: state.stats.rawPendingJobs,
            active: state.stats.rawActiveJobs,
            failed: state.stats.rawFailedJobs
        });
        
        // Update worker information if available
        if (statsData.workers && statsData.workers.list) {
            Object.entries(statsData.workers.list).forEach(([workerId, workerData]) => {
                // Update or add worker to state
                state.workers[workerId] = {
                    ...state.workers[workerId],
                    ...workerData,
                    id: workerId
                };
            });
        }
        
        // Update job information if available
        // Check for active_jobs array instead of list object
        if (statsData.jobs && statsData.jobs.active_jobs && Array.isArray(statsData.jobs.active_jobs)) {
            
            // Process each job in the active_jobs array
            // Note: active_jobs array includes jobs with status 'pending', 'active', and 'failed'
            statsData.jobs.active_jobs.forEach(jobData => {
                // Make sure we have a job ID
                const jobId = jobData.id;
                if (!jobId) {
                    console.warn('[WARNING] Job data missing ID:', jobData);
                    return; // Skip this job
                }
                
                // Log job status for debugging
                console.log(`[2025-04-06 18:31] Processing job ${jobId} with status: ${jobData.status}`);
                
                // Update or add job to state
                state.jobs[jobId] = {
                    ...state.jobs[jobId],
                    ...jobData,
                    id: jobId,
                    job_type: jobData.job_type || jobData.type || '',
                    priority: parseInt(jobData.priority || 0),
                    position: jobData.position || parseInt(jobData.priority || 0),  // Use priority as position if position is not available
                    // Ensure status is properly set
                    status: jobData.status || 'unknown'
                };
            });
            
            // Log total jobs processed
            console.log(`[2025-04-06 18:31] Processed ${statsData.jobs.active_jobs.length} jobs from active_jobs array`);
        } else {
            console.log('[DEBUG] No active_jobs array found in stats data');
        }
        
        // Refresh the UI with updated stats
        updateUI();
    } catch (error) {
        console.error('Error updating stats:', error);
        addLogEntry(`Error updating stats: ${error.message}`, 'error');
    }
}

/**
 * Handle stats response message
 * @param {Object} parsedMessage - Parsed stats response message
 * @param {Object} rawMessage - Raw message object (fallback)
 * @param {string} source - Source of the message ('monitor' or 'client')
 */
function handleStatsResponse(parsedMessage, rawMessage, source = 'unknown') {
    // Use parsed message if available, otherwise fallback to raw message
    const message = parsedMessage || rawMessage;
    const stats = message.stats || (rawMessage ? rawMessage.stats : {});
    
    if (!stats) {
        addLogEntry('Received stats response with no stats data', 'warning');
        return;
    }
    
    // Update the UI with the stats data
    updateStats(stats);
    
    // Log the receipt of stats
    addLogEntry('Received system statistics', 'success');
    
    // Mark any pending requests as completed
    if (state.pendingRequests) {
        // Find any pending stats requests and mark them as completed
        Object.keys(state.pendingRequests).forEach(requestId => {
            const request = state.pendingRequests[requestId];
            if (request.type === 'request_stats' && request.status === 'pending') {
                request.status = 'completed';
                request.completedAt = Date.now();
                console.log(`Marked stats request ${requestId} as completed`);
            }
        });
    }
}

/**
 * Handle acknowledgment message
 * @param {Object} parsedMessage - Parsed acknowledgment message
 * @param {Object} rawMessage - Raw message object (fallback)
 * @param {string} source - Source of the message ('monitor' or 'client')
 */
function handleAckMessage(parsedMessage, rawMessage, source = 'unknown') {
    // Use parsed message if available, otherwise fallback to raw message
    const message = parsedMessage || rawMessage;
    
    // Extract data from the ack message
    const originalId = message.originalId || message.original_id;
    const originalType = message.originalType || message.original_type;
    const messageId = message.message_id || message.messageId;
    
    // Update pending request status if this is acknowledging one of our requests
    if (state.pendingRequests && state.pendingRequests[originalId]) {
        state.pendingRequests[originalId].status = 'acknowledged';
        state.pendingRequests[originalId].ackTimestamp = message.timestamp;
        state.pendingRequests[originalId].source = source; // Track which connection acknowledged
        
        // Log detailed information for debugging
        console.log(`Request ${originalId} acknowledged by ${source} connection:`, state.pendingRequests[originalId]);
    }
    
    // Log the acknowledgment with appropriate detail level and source information
    if (originalType === 'request_stats') {
        // For stats requests, show a success message
        addLogEntry(`Server acknowledged our stats request via ${source} connection (ID: ${originalId})`, 'success');
    } else if (originalType === 'submit_job') {
        // For job submissions, show a success message
        addLogEntry(`Job submission acknowledged via ${source} connection (ID: ${originalId})`, 'success');
    } else if (originalType === 'stats_broadcast') {
        // For stats broadcasts, don't log to avoid cluttering the UI
        //console.log(`Received acknowledgment for stats broadcast via ${source}: ${originalId}`);
    } else {
        // For other message types, show a normal info message
        addLogEntry(`Received acknowledgment for ${originalType} message via ${source} (ID: ${originalId})`, 'info');
    }
}

/**
 * Handle stats broadcast message
 * @param {Object} parsedMessage - Parsed stats broadcast message
 * @param {Object} rawMessage - Raw message object (fallback)
 * @param {string} source - Source of the message ('monitor' or 'client')
 */
function handleStatsBroadcast(parsedMessage, rawMessage, source = 'unknown') {
    // Use parsed message if available, otherwise fallback to raw message
    const message = parsedMessage || rawMessage;
    
    // Extract data from the broadcast message - with the updated parser, these fields are directly available
    const connections = message.connections || {};
    const workers = message.workers || {};
    const system = message.system || {};
    
    // Log the received broadcast with detailed information
    addLogEntry(`Received stats broadcast with ${Object.keys(workers).length} workers and ${connections.clients ? connections.clients.length : 0} clients`, 'info');
    
    // [2025-05-23T09:45:00-04:00] Fixed issue with stale worker cards in the UI
    // First, save existing worker data to preserve important fields like current_job_id
    const existingWorkers = { ...state.workers };
    
    // Clear the workers state to start fresh - this ensures we only keep workers that are actually connected
    state.workers = {};
    
    // Get the list of actually connected workers from the connections data
    const connectedWorkerIds = connections.workers || [];
    
    // Log the connected workers for debugging
    console.log(`[2025-05-23T09:45:00-04:00] Connected workers from backend: ${connectedWorkerIds.length}`, connectedWorkerIds);
    
    // Only process workers that are actually connected according to the connections data
    Object.entries(workers).forEach(([workerId, workerData]) => {
        // Skip workers that aren't in the connected workers list
        if (!connectedWorkerIds.includes(workerId)) {
            console.log(`[2025-05-23T09:45:00-04:00] Skipping disconnected worker: ${workerId}`);
            return;
        }
        
        // Get existing worker data or create a new object
        const existingWorker = existingWorkers[workerId] || {};
        
        // Update or add worker to state, preserving existing properties
        state.workers[workerId] = {
            ...existingWorker,  // Keep existing properties
            id: workerId,
            status: workerData.status || existingWorker.status || 'unknown',
            connectedAt: existingWorker.connectedAt || Date.now(),
            jobsProcessed: workerData.jobs_processed || existingWorker.jobsProcessed || 0,
            is_accepting_jobs: system.workers && system.workers.active_workers ? 
                system.workers.active_workers.find(w => w.id === workerId) !== undefined : false,
            // Include worker capabilities
            capabilities: workerData.capabilities || existingWorker.capabilities || {},
            // Add any additional worker data that might be useful
            lastSeen: new Date().toLocaleTimeString(),
            // Preserve current job information
            current_job_id: existingWorker.current_job_id || null
        };
        
        console.log(`[2025-05-23T09:45:00-04:00] Added connected worker: ${workerId}`);
    });
    
    // Log the final worker count
    console.log(`[2025-05-23T09:45:00-04:00] Final worker count: ${Object.keys(state.workers).length}`);
    
    // Update client connections
    state.clients = {};
    if (connections.clients) {
        connections.clients.forEach(clientId => {
            state.clients[clientId] = {
                id: clientId,
                connectedAt: Date.now(), // We don't have the exact time
                lastSeen: new Date().toLocaleTimeString()
            };
        });
    }
    
    // Update monitor connections
    state.monitors = {};
    if (connections.monitors) {
        connections.monitors.forEach(monitorId => {
            state.monitors[monitorId] = {
                id: monitorId,
                connectedAt: Date.now(),
                lastSeen: new Date().toLocaleTimeString()
            };
        });
    }
    
    // Update stats with the actual number of connected workers
    state.stats.totalWorkers = Object.keys(state.workers).length;
    state.stats.totalClients = connections.clients ? connections.clients.length : 0;
    state.stats.totalMonitors = connections.monitors ? connections.monitors.length : 0;
    
    // Update job stats if available
    if (system && system.jobs) {
        // Update job counts
        state.stats.totalJobs = system.jobs.total || 0;
        state.stats.activeJobs = system.jobs.status?.processing || 0;
        state.stats.completedJobs = system.jobs.status?.completed || 0;
        state.stats.failedJobs = system.jobs.status?.failed || 0;
        
        // Update queue information
        if (system.queues) {
            state.stats.queuedJobs = system.queues.total || 0;
            state.stats.priorityJobs = system.queues.priority || 0;
            state.stats.standardJobs = system.queues.standard || 0;
        }
        
        // Process active jobs if available
        if (system.jobs && system.jobs.active_jobs && Array.isArray(system.jobs.active_jobs)) {
            
            // First, separate jobs into priority levels
            const jobsByPriority = {};
            system.jobs.active_jobs.forEach(jobData => {
                const priority = parseInt(jobData.priority || 0);
                if (!jobsByPriority[priority]) {
                    jobsByPriority[priority] = [];
                }
                jobsByPriority[priority].push(jobData);
            });
            
            // Get priority levels and sort them in descending order (highest priority first)
            const priorityLevels = Object.keys(jobsByPriority).map(Number).sort((a, b) => b - a);
            
            // Process jobs in priority order, then by creation time within each priority
            let position = 1; // Start positions at 1
            
            // Process each priority level in descending order
            priorityLevels.forEach(priority => {
                
                // Sort jobs within this priority by creation time (oldest first)
                jobsByPriority[priority].sort((a, b) => {
                    return (a.created_at || 0) - (b.created_at || 0);
                });
                
                // Process each job in this priority level
                jobsByPriority[priority].forEach(jobData => {
                    // Make sure we have a job ID
                    const jobId = jobData.id;
                    if (!jobId) {
                        console.warn('[WARNING] Job data missing ID:', jobData);
                        return; // Skip this job
                    }
                    
                    
                    // Parse the priority value
                    const parsedPriority = parseInt(jobData.priority || 0);
                    
                    // Update or add job to state with explicit field mapping
                    state.jobs[jobId] = {
                        ...state.jobs[jobId],
                        ...jobData,
                        id: jobId,
                        job_type: jobData.job_type || jobData.type || '',
                        priority: parsedPriority,
                        position: position++, // Assign position and increment for next job
                        createdAt: jobData.created_at ? new Date(jobData.created_at * 1000) : new Date(),
                        updatedAt: jobData.updated_at ? new Date(jobData.updated_at * 1000) : new Date()
                    };
                    
                });
            });
        } else {
            console.log('[DEBUG] No active_jobs array found in stats broadcast data');
        }
    }
    
    // Update subscriptions if available
    if (message.subscriptions) {
        state.subscriptions = message.subscriptions;
    }
    
    // Update UI
    updateUI();
}

/**
 * [2025-05-24T23:25:00-04:00] Handle job accepted message
 * @param {Object} message - Parsed job accepted message
 * @param {string} source - Source of the message ('monitor' or 'client')
 */
function handleJobAccepted(message, source = 'unknown') {
    const jobId = message.jobId || message.job_id;
    const status = message.status;
    const position = message.position;
    const jobType = message.job_type || message.type || null;
    const clientId = message.client_id || null;
    // [2025-05-24T23:25:00-04:00] Capture payload from the message
    const payload = message.payload || null;
    
    console.log(`[DEBUG] Job accepted: ${jobId}, type: ${jobType || 'unknown'}, client: ${clientId || 'unknown'}, source: ${source}`);
    console.log(`[DEBUG] Job payload:`, payload);
    
    // Add job to state
    state.jobs[jobId] = {
        id: jobId,
        status: status || 'pending',
        position: position,
        progress: 0,
        job_type: jobType,
        client_id: clientId,
        // [2025-05-24T23:25:00-04:00] Store payload
        payload: payload,
        createdAt: new Date(),
        updatedAt: new Date(),
        source_update: source
    };
    
    addLogEntry(`Job accepted: ${jobId} (Type: ${jobType || 'unknown'}, Client: ${clientId || 'unknown'})`, 'success');
}

/**
 * Handle job cancellation message
 * @param {Object} message - Parsed job cancellation message
 * @param {Object} rawMessage - Raw message object (fallback)
 * @param {string} source - Source of the message ('monitor' or 'client')
 * [2025-04-06 19:40] Added to handle job cancellations
 * [2025-04-06 20:50] Added job_type and client_id capture and preservation
 */
function handleJobCancelled(message, rawMessage, source = 'unknown') {
    // [2025-04-06 19:40] Handle both jobId (camelCase) and job_id (snake_case) formats
    const jobId = message.jobId || message.job_id || (rawMessage && (rawMessage.jobId || rawMessage.job_id));
    const workerId = message.workerId || message.worker_id || (rawMessage && (rawMessage.workerId || rawMessage.worker_id));
    const reason = message.reason || (rawMessage && rawMessage.reason) || 'No reason provided';
    // [2025-04-06 20:50] Capture job_type from the message
    const jobType = message.job_type || message.type || (rawMessage && (rawMessage.job_type || rawMessage.type)) || null;
    // [2025-04-06 20:50] Capture client_id from the message
    const clientId = message.client_id || (rawMessage && rawMessage.client_id) || null;
    
    console.log(`[DEBUG] Job cancellation received for jobId: ${jobId}, type: ${jobType || 'unknown'}, workerId: ${workerId}, client: ${clientId || 'unknown'}, source: ${source}`);
    addLogEntry(`Job cancelled: ${jobId} (Type: ${jobType || 'unknown'}) - ${reason}`, 'warning');
    
    // Update the job in state
    if (jobId) {
        // Create job if it doesn't exist yet
        if (!state.jobs[jobId]) {
            console.log(`[DEBUG] Creating new cancelled job in state for ${jobId}`);
            state.jobs[jobId] = {
                id: jobId,
                worker_id: workerId,
                client_id: clientId, // [2025-04-06 20:50] Store client ID
                job_type: jobType, // [2025-04-06 20:50] Store job type
                status: 'cancelled',
                progress: 0,
                createdAt: message.createdAt || message.created_at || (rawMessage && (rawMessage.createdAt || rawMessage.created_at)) || (Date.now() - 60000), // Default to 1 minute ago if no creation time
                cancelledAt: message.cancelledAt || message.cancelled_at || (rawMessage && (rawMessage.cancelledAt || rawMessage.cancelled_at)) || Date.now(),
                updated_at: Date.now(),
                reason: reason
            };
        } else {
            // Log before update
            console.log(`[DEBUG] Before cancellation update, job status:`, state.jobs[jobId].status);
            
            // Update job properties
            state.jobs[jobId].status = 'cancelled';
            state.jobs[jobId].updated_at = Date.now();
            state.jobs[jobId].cancelledAt = message.cancelledAt || message.cancelled_at || (rawMessage && (rawMessage.cancelledAt || rawMessage.cancelled_at)) || Date.now();
            state.jobs[jobId].reason = reason;
            
            // [2025-04-06 20:50] Update client_id if it's provided and not already set
            if (clientId && !state.jobs[jobId].client_id) {
                state.jobs[jobId].client_id = clientId;
                console.log(`[DEBUG] Updated client_id for job ${jobId} to ${clientId}`);
            }
            
            // [2025-04-06 20:50] Update job_type if it's provided and not already set
            if (jobType && (!state.jobs[jobId].job_type && !state.jobs[jobId].type)) {
                state.jobs[jobId].job_type = jobType;
                console.log(`[DEBUG] Updated job_type for job ${jobId} to ${jobType}`);
            }
            
            // Calculate duration if possible
            if (state.jobs[jobId].createdAt || state.jobs[jobId].created_at) {
                const startTime = state.jobs[jobId].createdAt || state.jobs[jobId].created_at;
                const endTime = state.jobs[jobId].cancelledAt || state.jobs[jobId].cancelled_at || Date.now();
                state.jobs[jobId].duration = Math.floor((endTime - startTime) / 1000); // Duration in seconds
            }
            
            console.log(`[DEBUG] Job ${jobId} marked as cancelled with reason: ${reason}`);
        }
        
        // Update worker's current_job_id if needed
        if (workerId && state.workers[workerId] && state.workers[workerId].current_job_id === jobId) {
            console.log(`[DEBUG] Clearing worker ${workerId} current_job_id as job has been cancelled`);
            state.workers[workerId].current_job_id = null;
        }
        
        // Log after update
        console.log(`[DEBUG] After cancellation update, job:`, state.jobs[jobId]);
    } else {
        console.log(`[DEBUG] Job cancellation update missing job ID`, message);
    }
    
    // Update the UI
    updateUI();
}

/**
 * Handle job failure message
 * @param {Object} message - Parsed job failure message
 * @param {Object} rawMessage - Raw message object (fallback)
 * @param {string} source - Source of the message ('monitor' or 'client')
 * [2025-04-06 19:35] Added to properly handle job failures
 * [2025-04-06 20:50] Added job_type and client_id capture and preservation
 */
function handleJobFailed(message, rawMessage, source = 'unknown') {
    // [2025-04-06 19:35] Handle both jobId (camelCase) and job_id (snake_case) formats
    const jobId = message.jobId || message.job_id || (rawMessage && (rawMessage.jobId || rawMessage.job_id));
    const workerId = message.workerId || message.worker_id || (rawMessage && (rawMessage.workerId || rawMessage.worker_id));
    const error = message.error || (rawMessage && rawMessage.error) || 'Unknown error';
    // [2025-04-06 20:50] Capture job_type from the message
    const jobType = message.job_type || message.type || (rawMessage && (rawMessage.job_type || rawMessage.type)) || null;
    // [2025-04-06 20:50] Capture client_id from the message
    const clientId = message.client_id || (rawMessage && rawMessage.client_id) || null;
    
    console.log(`[DEBUG] Job failure received for jobId: ${jobId}, type: ${jobType || 'unknown'}, workerId: ${workerId}, client: ${clientId || 'unknown'}, source: ${source}`);
    addLogEntry(`Job failed: ${jobId} (Type: ${jobType || 'unknown'}) - ${error}`, 'error');
    
    // Update the job in state
    if (jobId) {
        // Create job if it doesn't exist yet
        if (!state.jobs[jobId]) {
            console.log(`[DEBUG] Creating new failed job in state for ${jobId}`);
            state.jobs[jobId] = {
                id: jobId,
                worker_id: workerId,
                client_id: clientId, // [2025-04-06 20:50] Store client ID
                job_type: jobType, // [2025-04-06 20:50] Store job type
                status: 'failed',
                progress: 0,
                createdAt: message.createdAt || message.created_at || (rawMessage && (rawMessage.createdAt || rawMessage.created_at)) || (Date.now() - 60000), // Default to 1 minute ago if no creation time
                failedAt: message.failedAt || message.failed_at || (rawMessage && (rawMessage.failedAt || rawMessage.failed_at)) || Date.now(),
                updated_at: Date.now(),
                error: error
            };
        } else {
            // Log before update
            console.log(`[DEBUG] Before failure update, job status:`, state.jobs[jobId].status);
            
            // Update job properties
            state.jobs[jobId].status = 'failed';
            state.jobs[jobId].updated_at = Date.now();
            state.jobs[jobId].failedAt = message.failedAt || message.failed_at || (rawMessage && (rawMessage.failedAt || rawMessage.failed_at)) || Date.now();
            state.jobs[jobId].error = error;
            
            // [2025-04-06 20:50] Update client_id if it's provided and not already set
            if (clientId && !state.jobs[jobId].client_id) {
                state.jobs[jobId].client_id = clientId;
                console.log(`[DEBUG] Updated client_id for job ${jobId} to ${clientId}`);
            }
            
            // [2025-04-06 20:50] Update job_type if it's provided and not already set
            if (jobType && (!state.jobs[jobId].job_type && !state.jobs[jobId].type)) {
                state.jobs[jobId].job_type = jobType;
                console.log(`[DEBUG] Updated job_type for job ${jobId} to ${jobType}`);
            }
            
            // Calculate duration if possible
            if (state.jobs[jobId].createdAt || state.jobs[jobId].created_at) {
                const startTime = state.jobs[jobId].createdAt || state.jobs[jobId].created_at;
                const endTime = state.jobs[jobId].failedAt || state.jobs[jobId].failed_at || Date.now();
                state.jobs[jobId].duration = Math.floor((endTime - startTime) / 1000); // Duration in seconds
            }
            
            console.log(`[DEBUG] Job ${jobId} marked as failed with error: ${error}`);
        }
        
        // Update worker's current_job_id if needed
        if (workerId && state.workers[workerId] && state.workers[workerId].current_job_id === jobId) {
            console.log(`[DEBUG] Clearing worker ${workerId} current_job_id as job has failed`);
            state.workers[workerId].current_job_id = null;
        }
        
        // Log after update
        console.log(`[DEBUG] After failure update, job:`, state.jobs[jobId]);
    } else {
        console.log(`[DEBUG] Job failure update missing job ID`, message);
    }
    
    // Update the UI
    updateUI();
}

/**
 * [2025-05-24T23:35:00-04:00] Handle job completion message
 * @param {Object} message - Parsed job completion message
 * @param {string} source - Source of the message ('monitor' or 'client')
 */
function handleJobCompleted(message, source = 'unknown') {
    // Extract job details from message
    const jobId = message.jobId || message.job_id;
    const workerId = message.workerId || message.worker_id;
    const result = message.result || {};
    const clientId = message.client_id || null;
    const jobType = message.job_type || message.type || null;
    // [2025-05-24T23:35:00-04:00] Capture payload from the message
    const payload = message.payload || null;

    // Log the completion with job type
    console.log(`[DEBUG] Job completed: ${jobId} (type: ${jobType || 'unknown'}) by worker ${workerId}, client: ${clientId}`);
    addLogEntry(`Job completed: ${jobId} (Type: ${jobType || 'unknown'}, Client: ${clientId || 'unknown'})`, 'success');

    // Update the job in state or create if it doesn't exist
    if (jobId) {
        if (!state.jobs[jobId]) {
            // Create a placeholder job if we don't have it yet
            state.jobs[jobId] = {
                id: jobId,
                worker_id: workerId,
                client_id: clientId,
                job_type: jobType,
                status: 'completed',
                progress: 100,
                result: result,
                // [2025-05-24T23:40:00-04:00] Store payload data
                payload: payload,
                createdAt: Date.now() - 1000, // Assume it was created a second ago
                completedAt: Date.now(),
                updated_at: Date.now(),
                isPlaceholder: true, // Mark as placeholder for future updates
                source_update: source
            };
            console.log(`[DEBUG] Created placeholder completed job for ${jobId} with type ${jobType || 'unknown'}`);
        } else {
            // Update existing job
            state.jobs[jobId].status = 'completed';
            state.jobs[jobId].progress = 100;
            state.jobs[jobId].result = result;
            state.jobs[jobId].completedAt = Date.now();
            state.jobs[jobId].updated_at = Date.now();
            state.jobs[jobId].worker_id = workerId;
            state.jobs[jobId].source_update = source;

            // [2025-05-24T23:45:00-04:00] Update payload if it's provided and not already set
            if (payload && !state.jobs[jobId].payload) {
                state.jobs[jobId].payload = payload;
                console.log(`[DEBUG] Updated payload for job ${jobId}`);
            }

            // Update client_id if it's provided and not already set
            if (clientId && !state.jobs[jobId].client_id) {
                state.jobs[jobId].client_id = clientId;
                console.log(`[DEBUG] Updated client_id for job ${jobId} to ${clientId}`);
            }
            
            // Update job_type if it's provided and not already set
            if (jobType && (!state.jobs[jobId].job_type && !state.jobs[jobId].type)) {
                state.jobs[jobId].job_type = jobType;
                console.log(`[DEBUG] Updated job_type for job ${jobId} to ${jobType}`);
            }

            // [2025-04-07 23:47] Calculate and store job duration based on processing start time
            // Use processingStartedAt (when job was accepted by worker) instead of createdAt
            // This provides a more accurate measure of actual processing time
            const startTime = state.jobs[jobId].processingStartedAt 
                ? new Date(state.jobs[jobId].processingStartedAt).getTime()
                : state.jobs[jobId].createdAt;

            if (startTime) {
                const durationMs = Date.now() - startTime;
                // Convert to seconds for the formatDuration function
                const durationSec = Math.floor(durationMs / 1000);
                state.jobs[jobId].duration = durationSec;
                const startType = state.jobs[jobId].processingStartedAt ? "processing start" : "creation";
                console.log(`[DEBUG] Job ${jobId} completed in ${durationSec}s (${durationMs}ms) from ${startType}`);
            }

            console.log(`[DEBUG] Updated job ${jobId} to completed status`);
        }

        // If this worker is assigned to this job, update its status
        if (workerId && state.workers[workerId]) {
            if (state.workers[workerId].current_job_id === jobId) {
                state.workers[workerId].current_job_id = null;
                state.workers[workerId].status = 'idle';
                console.log(`[DEBUG] Updated worker ${workerId} status to idle`);
            }
        }

        // Show notification for job completion
        showNotification(`Job ${jobId} completed successfully`, 'success');
    } else {
        console.log(`[DEBUG] Job completion message missing job ID`, message);
    }

    // Update the UI
    updateUI();
}

/**
 * Handle job progress update message
 * @param {Object} message - Parsed job progress message
 * @param {string} source - Source of the message ('monitor' or 'client')
 * [2025-04-06 19:32] Enhanced to prioritize client updates and preserve detailed job information
 * [2025-04-06 20:40] Added client_id capture from monitor messages
 */
function handleJobProgress(message, source = 'unknown') {
    // [2025-04-06 19:23] Fixed property name mismatch between camelCase and snake_case
    // Handle both jobId (camelCase) and job_id (snake_case) formats
    const jobId = message.jobId || message.job_id;
    const workerId = message.workerId || message.worker_id;
    const progress = message.progress || 0;
    const status = message.status || 'processing';
    // [2025-04-06 20:40] Capture client_id from the message
    const clientId = message.client_id || null;
    // [2025-05-24T23:30:00-04:00] Get payload from message if available
    const payload = message.payload || null;
    // [2025-05-25T11:00:00-04:00] Get message text for special service request detection
    const messageText = message.message || '';
    
    // [2025-05-25T11:00:00-04:00] Check if this is a special service request message
    if (status === 'service_request' && messageText.startsWith('SERVICE_REQUEST:')) {
        console.log(`[2025-05-25T11:00:00-04:00] Detected service request message for job ${jobId}`);
        
        try {
            // Parse the service request message
            // Format: SERVICE_REQUEST:<endpoint>:<method>:<url>:<payload_json>
            const parts = messageText.split(':');
            if (parts.length >= 5) {
                const endpoint = parts[1];
                const method = parts[2];
                const url = parts[3];
                // Rejoin the remaining parts as they might contain colons within the JSON
                const payloadJson = parts.slice(4).join(':');
                let requestPayload = {};
                
                try {
                    requestPayload = JSON.parse(payloadJson);
                } catch (e) {
                    console.error(`[2025-05-25T11:00:00-04:00] Error parsing service request payload: ${e.message}`);
                }
                
                // Create a service request message in the format expected by handleServiceRequest
                const serviceRequestMessage = {
                    type: 'service_request',
                    timestamp: Date.now(),
                    job_id: jobId,
                    worker_id: workerId,
                    service: 'a1111', // Hardcoded for now since we know it's from A1111 connector
                    request_type: `a1111_${endpoint}`,
                    content: {
                        endpoint: endpoint,
                        method: method,
                        url: url,
                        payload: requestPayload
                    }
                };
                
                // Handle the service request using the existing handler
                console.log(`[2025-05-25T11:00:00-04:00] Forwarding to handleServiceRequest: ${endpoint}, ${method}, ${url}`);
                handleServiceRequest(serviceRequestMessage, source);
                return; // Skip normal progress update handling
            }
        } catch (e) {
            console.error(`[2025-05-25T11:00:00-04:00] Error processing service request message: ${e.message}`);
        }
    }
    
    console.log(`[DEBUG] Job progress update received with jobId: ${jobId}, workerId: ${workerId}, clientId: ${clientId}, source: ${source}`);
    addLogEntry(`Job progress update: ${jobId} - ${progress}% (Client: ${clientId || 'unknown'})`, 'info');
    
    // Update the job in state
    if (jobId) {
        // Create job if it doesn't exist yet
        if (!state.jobs[jobId]) {
            console.log(`[DEBUG] Creating new job in state for ${jobId}`);
            state.jobs[jobId] = {
                id: jobId,
                worker_id: workerId,
                client_id: clientId, // [2025-04-06 20:40] Store client ID
                status: status,
                progress: progress,
                createdAt: Date.now(),
                updated_at: Date.now(),
                source_update: source,  // Track which source last updated this job
                // [2025-05-24T23:30:00-04:00] Store payload if available
                payload: payload
            };
        } else {
            // Log before update
            console.log(`[DEBUG] Before update, job status:`, state.jobs[jobId].status);
            
            // [2025-05-20T11:58:19-04:00] Ignore progress updates for completed jobs
            // This prevents the A1111 connector's final 10% progress update from reverting completed jobs
            if (state.jobs[jobId].status === 'completed' || state.jobs[jobId].status === 'failed') {
                console.log(`[2025-05-20T11:58:19-04:00] Ignoring progress update for ${state.jobs[jobId].status} job ${jobId}`);
                addLogEntry(`Ignored progress update for ${state.jobs[jobId].status} job ${jobId}`, 'info');
                return;
            }
            
            // [2025-04-06 20:40] Always apply monitor updates since we're only using monitor connection
            console.log(`[DEBUG] Applying monitor update to job ${jobId}`);
            state.jobs[jobId].progress = progress;
            state.jobs[jobId].updated_at = Date.now();
            state.jobs[jobId].worker_id = workerId;
            state.jobs[jobId].source_update = source;
            
            // [2025-04-06 20:40] Update client_id if it's provided and not already set
            if (clientId && !state.jobs[jobId].client_id) {
                state.jobs[jobId].client_id = clientId;
                console.log(`[DEBUG] Updated client_id for job ${jobId} to ${clientId}`);
            }
            
            // If this was a placeholder, it's not anymore since we have real data
            if (state.jobs[jobId].isPlaceholder) {
                delete state.jobs[jobId].isPlaceholder;
            }
            
            // [2025-04-06 20:10] Ensure job is marked as active/processing when we get progress updates
            // Also track when the job actually starts processing for accurate time estimation
            if (state.jobs[jobId].status !== 'processing' && state.jobs[jobId].status !== 'active') {
                console.log(`[DEBUG] Updating job status from ${state.jobs[jobId].status} to 'processing'`);
                state.jobs[jobId].status = 'processing';
                
                // Record the exact time when the job starts processing
                // This is critical for accurate completion time estimation
                state.jobs[jobId].processingStartedAt = new Date().toISOString();
                console.log(`[DEBUG] Job ${jobId} started processing at ${state.jobs[jobId].processingStartedAt}`);
            }
        }
        
        // Update worker's current_job_id if needed
        if (workerId && state.workers[workerId]) {
            if (state.workers[workerId].current_job_id !== jobId) {
                console.log(`[DEBUG] Updating worker ${workerId} current_job_id to ${jobId}`);
                state.workers[workerId].current_job_id = jobId;
            }
        }
        
        // Log after update
        console.log(`[DEBUG] After update, job:`, state.jobs[jobId]);
    } else {
        console.log(`[DEBUG] Job progress update missing job ID`, message);
    }
    
    // Update the UI
    updateUI();
}

/**
 * Handle worker status update message
 * @param {Object} message - Parsed worker status message
 * @param {string} source - Source of the message ('monitor' or 'client')
 */
function handleWorkerStatus(message, source = 'unknown') {
    // [2025-04-06 19:23] Fixed property name mismatch between camelCase and snake_case
    // Handle both workerId (camelCase) and worker_id (snake_case) formats
    const workerId = message.workerId || message.worker_id;
    const status = message.status || 'unknown';
    const currentJobId = message.currentJobId || message.current_job_id;
    
    console.log(`[DEBUG] Worker status update received for worker: ${workerId}, status: ${status}`);
    addLogEntry(`Worker status update: ${workerId} - ${status}`, 'info');
    
    // Update the worker in state
    if (workerId) {
        // Check if worker exists in state
        if (state.workers[workerId]) {
            // Log before update
            console.log(`[DEBUG] Before update, worker:`, {
                status: state.workers[workerId].status,
                current_job_id: state.workers[workerId].current_job_id
            });
            
            // Update worker properties
            state.workers[workerId].status = status;
            state.workers[workerId].updated_at = Date.now();
            
            // Update current job if provided
            if (currentJobId) {
                state.workers[workerId].current_job_id = currentJobId;
                
                // Make sure the job exists in our state and is properly linked to this worker
                if (state.jobs[currentJobId]) {
                    state.jobs[currentJobId].worker_id = workerId;
                    
                    // Ensure job is marked as processing if it's assigned to a worker
                    if (state.jobs[currentJobId].status !== 'processing' && 
                        state.jobs[currentJobId].status !== 'active') {
                        console.log(`[DEBUG] Updating job ${currentJobId} status to 'processing'`);
                        state.jobs[currentJobId].status = 'processing';
                    }
                } else {
                    console.log(`[DEBUG] Worker has current_job_id ${currentJobId} but job not found in state`);
                    
                    // Create a placeholder job if it doesn't exist
                    // [2025-04-06 19:32] Added a flag to indicate this is a placeholder job
                    // This helps us prioritize client updates which have more detailed information
                    state.jobs[currentJobId] = {
                        id: currentJobId,
                        worker_id: workerId,
                        status: 'processing',
                        progress: 0,
                        createdAt: Date.now(),
                        updated_at: Date.now(),
                        isPlaceholder: true  // Flag to indicate this is a placeholder with minimal info
                    };
                    console.log(`[DEBUG] Created placeholder job for ${currentJobId}`);
                }
            }
        } else {
            // Create worker if it doesn't exist
            console.log(`[DEBUG] Creating new worker: ${workerId}`);
            state.workers[workerId] = {
                id: workerId,
                status: status,
                connectedAt: Date.now(),
                updated_at: Date.now(),
                current_job_id: currentJobId || null,
                jobsProcessed: 0,
                is_accepting_jobs: true
            };
            
            // If worker has a current job, make sure it exists
            if (currentJobId && !state.jobs[currentJobId]) {
                state.jobs[currentJobId] = {
                    id: currentJobId,
                    worker_id: workerId,
                    status: 'processing',
                    progress: 0,
                    createdAt: Date.now(),
                    updated_at: Date.now()
                };
                console.log(`[DEBUG] Created placeholder job for new worker: ${currentJobId}`);
            }
        }
        
        // Log after update
        console.log(`[DEBUG] After update, worker:`, {
            status: state.workers[workerId].status,
            current_job_id: state.workers[workerId].current_job_id
        });
    } else {
        console.log(`[DEBUG] Worker status update missing worker ID`, message);
    }
    
    // Update the UI
    updateUI();
}

/**
 * Handle error message
 * @param {Object} message - Parsed error message
 * @param {string} source - Source of the message ('monitor' or 'client')
 */
function handleErrorMessage(message, source = 'unknown') {
    // Extract error information, handling different message formats
    const error = message.error || (message.originalMessage ? message.originalMessage.error : 'Unknown error');
    const details = message.details || (message.originalMessage ? message.originalMessage.details : undefined);
    const originalType = message.originalType || (message.originalMessage ? message.originalMessage.original_type : undefined);
    
    // [2025-05-20T11:23:31-04:00] Special handling for unsupported message types
    if (error && (error.includes('Unsupported message type: request_stats') || 
                  error.includes('Unsupported message type: subscribe_stats'))) {
        // These are expected errors when using the Request Stats button
        // The server doesn't support these message types, but we can ignore these errors
        // We've updated the requestStats function to not send these messages
        console.log(`[2025-05-20T11:23:31-04:00] Ignoring expected error for unsupported message type: ${error}`);
        return;
    }
    
    // Create a more detailed error message
    let errorMessage = `Error: ${error}`;
    if (originalType) {
        errorMessage += ` (related to message type: ${originalType})`;
    }
    
    // Log the error with appropriate details
    addLogEntry(errorMessage, 'error');
    console.error('Error message:', error, details);
}

/**
 * [2025-05-20T11:34:47-04:00] Check the status of a job via REST API
 * @param {string} jobId - The ID of the job to check
 * @returns {Promise<Object>} - The job status data
 */
async function checkJobStatus(jobId) {
    try {
        // Check if REST API is enabled
        if (!state.restApi.enabled) {
            throw new Error('REST API is not enabled');
        }
        
        // Make the REST API request to check job status
        const response = await fetch(`${state.restApi.url}/${jobId}`, {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            }
        });
        
        // Check if request was successful
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `HTTP error ${response.status}`);
        }
        
        // Parse and return response
        return await response.json();
    } catch (error) {
        console.error(`[2025-05-20T11:34:47-04:00] Error checking job status for ${jobId}:`, error);
        throw error;
    }
}

/**
 * [2025-05-20T13:51:20-04:00] Display REST API response
 * This function updates the REST response container with the given content
 * The fixed layout structure prevents any layout shifts
 */
/**
 * [2025-05-24T12:51:00-04:00] Display REST API response with maximize button for JSON viewing
 * @param {string} content - The response content to display
 * @param {boolean} isError - Whether the response is an error
 */
function displayRestResponse(content, isError = false) {
    // Update the response content
    elements.restResponse.textContent = content;
    
    // Apply styling based on whether it's an error
    if (isError) {
        elements.restResponse.classList.add('error-response');
    } else {
        elements.restResponse.classList.remove('error-response');
    }
    
    // Add a subtle highlight effect to draw attention without moving the layout
    elements.restResponseContainer.classList.add('highlight-container');
    setTimeout(() => {
        elements.restResponseContainer.classList.remove('highlight-container');
    }, 1500);
    
    // [2025-05-24T12:51:30-04:00] Add maximize button if it doesn't exist
    let maximizeBtn = document.getElementById('rest-response-maximize');
    if (!maximizeBtn) {
        // Create the maximize button
        maximizeBtn = document.createElement('button');
        maximizeBtn.id = 'rest-response-maximize';
        maximizeBtn.className = 'maximize-btn';
        maximizeBtn.innerHTML = '⤢'; // Unicode maximize icon
        maximizeBtn.title = 'View in larger modal (Ctrl+M)';
        
        // Add the button to the container
        const responseHeader = elements.restResponseContainer.querySelector('.response-header');
        if (responseHeader) {
            responseHeader.appendChild(maximizeBtn);
        } else {
            elements.restResponseContainer.insertBefore(maximizeBtn, elements.restResponse);
        }
        
        // Add click event to open modal
        maximizeBtn.addEventListener('click', () => showRestResponseModal(content));
    }
    
    // Update the button's onclick to use the current content
    maximizeBtn.onclick = () => showRestResponseModal(content);
}

/**
 * [2025-05-24T12:52:00-04:00] Show REST API response in a modal for better viewing
 * @param {string} content - The content to display in the modal
 */
function showRestResponseModal(content) {
    // Create modal if it doesn't exist
    let modal = elements.restResponseModal;
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'rest-response-modal';
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal-content rest-modal-content">
                <div class="modal-header">
                    <h2>REST API Response</h2>
                    <div class="modal-actions">
                        <button id="rest-response-modal-copy" class="copy-btn" title="Copy to clipboard (Ctrl+C)">📋 Copy</button>
                        <span class="copy-feedback" id="copy-feedback">Copied!</span>
                        <button id="rest-response-modal-close" class="close-button" title="Close (Escape)">×</button>
                    </div>
                </div>
                <pre id="rest-response-modal-content" class="modal-json-content"></pre>
            </div>
        `;
        document.body.appendChild(modal);
        
        // Store references to modal elements
        elements.restResponseModal = modal;
        elements.restResponseModalContent = document.getElementById('rest-response-modal-content');
        elements.restResponseModalClose = document.getElementById('rest-response-modal-close');
        elements.restResponseModalCopy = document.getElementById('rest-response-modal-copy');
        
        // Add event listeners
        elements.restResponseModalClose.addEventListener('click', () => {
            modal.style.display = 'none';
        });
        
        elements.restResponseModalCopy.addEventListener('click', () => {
            copyToClipboard(elements.restResponseModalContent.textContent);
        });
        
        // Close modal when clicking outside of it
        window.addEventListener('click', (event) => {
            if (event.target === modal) {
                modal.style.display = 'none';
            }
        });
        
        // Add keyboard shortcuts
        window.addEventListener('keydown', (event) => {
            if (modal.style.display === 'block') {
                // Close on Escape
                if (event.key === 'Escape') {
                    modal.style.display = 'none';
                }
                
                // Copy on Ctrl+C
                if (event.ctrlKey && event.key === 'c') {
                    copyToClipboard(elements.restResponseModalContent.textContent);
                    event.preventDefault();
                }
            }
        });
        
        // Add CSS for modal
        const style = document.createElement('style');
        style.textContent = `
            .modal {
                display: none;
                position: fixed;
                z-index: 1000;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0,0,0,0.5);
            }
            .rest-modal-content {
                background-color: white;
                margin: 5% auto;
                padding: 0;
                border-radius: 5px;
                width: 90%;
                max-width: 1200px;
                max-height: 90vh;
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }
            .modal-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 10px 20px;
                background-color: #f5f5f5;
                border-bottom: 1px solid #ddd;
            }
            .modal-actions {
                display: flex;
                align-items: center;
                gap: 10px;
            }
            .modal-json-content {
                padding: 20px;
                overflow: auto;
                flex: 1;
                margin: 0;
                background-color: #f8f8f8;
                font-family: monospace;
                font-size: 14px;
                white-space: pre-wrap;
                max-height: calc(90vh - 60px);
            }
            .copy-btn {
                padding: 5px 10px;
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 3px;
                cursor: pointer;
                display: flex;
                align-items: center;
                gap: 5px;
            }
            .copy-btn:hover {
                background-color: #e0e0e0;
            }
            .copy-feedback {
                color: #4CAF50;
                font-size: 14px;
                opacity: 0;
                transition: opacity 0.3s;
            }
            .copy-feedback.visible {
                opacity: 1;
            }
            .maximize-btn {
                background: none;
                border: none;
                font-size: 18px;
                cursor: pointer;
                color: #555;
                margin-left: 10px;
                vertical-align: middle;
            }
            .maximize-btn:hover {
                color: #000;
            }
            .response-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
            }
        `;
        document.head.appendChild(style);
    }
    
    // Update modal content with formatted JSON if possible
    try {
        // Try to parse and re-stringify the content for pretty formatting
        const jsonObj = JSON.parse(content);
        elements.restResponseModalContent.textContent = JSON.stringify(jsonObj, null, 2);
    } catch (e) {
        // If not valid JSON, just display the content as is
        elements.restResponseModalContent.textContent = content;
    }
    
    // Show modal
    modal.style.display = 'block';
}

/**
 * [2025-05-24T12:53:00-04:00] Copy content to clipboard with feedback
 * @param {string} text - The text to copy to clipboard
 */
function copyToClipboard(text) {
    // Use the Clipboard API if available
    if (navigator.clipboard) {
        navigator.clipboard.writeText(text)
            .then(() => showCopyFeedback())
            .catch(err => console.error('Could not copy text: ', err));
    } else {
        // Fallback for browsers that don't support Clipboard API
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = 0;
        document.body.appendChild(textarea);
        textarea.select();
        
        try {
            const successful = document.execCommand('copy');
            if (successful) {
                showCopyFeedback();
            } else {
                console.error('Failed to copy');
            }
        } catch (err) {
            console.error('Error copying text: ', err);
        }
        
        document.body.removeChild(textarea);
    }
}

/**
 * [2025-05-24T12:53:30-04:00] Show feedback when content is copied
 */
function showCopyFeedback() {
    const feedback = document.getElementById('copy-feedback');
    if (feedback) {
        feedback.classList.add('visible');
        setTimeout(() => {
            feedback.classList.remove('visible');
        }, 2000);
    }
}

/**
 * [2025-05-20T11:40:07-04:00] Check job status from the UI
 * This function is called when the user clicks the "Check Status" button
 */
async function checkJobStatusFromUI() {
    try {
        // Get job ID from input field
        const jobId = elements.jobStatusId.value.trim();

        
        // Validate job ID
        if (!jobId) {
            showNotification('Please enter a job ID', 'error');
            return;
        }
        
        // Show loading state
        elements.checkJobStatusBtn.disabled = true;
        elements.checkJobStatusBtn.textContent = 'Checking...';
        
        // Check job status
        const jobStatus = await checkJobStatus(jobId);
        
        // [2025-05-25T09:15:00-04:00] Store job data in state for access in job details modal
        // This ensures the payload is available when viewing job details
        if (jobStatus && jobStatus.job_id) {
            // Store or update the job in state
            if (!state.jobs[jobStatus.job_id]) {
                state.jobs[jobStatus.job_id] = {
                    id: jobStatus.job_id,
                    status: jobStatus.status,
                    job_type: jobStatus.job_type || jobStatus.type,
                    worker_id: jobStatus.worker_id,
                    client_id: jobStatus.client_id,
                    priority: jobStatus.priority,
                    progress: jobStatus.progress,
                    createdAt: jobStatus.created_at,
                    updated_at: jobStatus.updated_at,
                    // Store the payload data
                    payload: jobStatus.payload,
                    result: jobStatus.result,
                    error: jobStatus.error,
                    source_update: 'rest_api'
                };
                console.log(`[2025-05-25T09:15:00-04:00] Created job state for ${jobStatus.job_id} from REST API with payload:`, jobStatus.payload);
            } else {
                // Update existing job, preserving payload if it exists
                const existingJob = state.jobs[jobStatus.job_id];
                state.jobs[jobStatus.job_id] = {
                    ...existingJob,
                    status: jobStatus.status,
                    worker_id: jobStatus.worker_id,
                    progress: jobStatus.progress,
                    updated_at: jobStatus.updated_at,
                    // Preserve existing payload or use the new one
                    payload: jobStatus.payload || existingJob.payload,
                    result: jobStatus.result || existingJob.result,
                    error: jobStatus.error || existingJob.error,
                    source_update: 'rest_api'
                };
                console.log(`[2025-05-25T09:15:00-04:00] Updated job state for ${jobStatus.job_id} from REST API with payload:`, jobStatus.payload || existingJob.payload);
            }
        }
        
        // [2025-05-20T13:41:23-04:00] Format the job status response for better readability
        // Make a copy of the job status to modify for display
        const displayJobStatus = {...jobStatus};
        
        // Format the position to be more user-friendly
        if (displayJobStatus.status === 'pending' && displayJobStatus.position !== undefined) {
            // [2025-05-23T19:48:33-04:00] Updated to work with 0-based positions from backend
            if (displayJobStatus.position === 0) {
                // Position 0 means this job is next up
                displayJobStatus.display_position = 1;
                displayJobStatus.position_description = 'Next up';
            } else {
                // For other positions, add 1 to display position (to make it 1-based for display only)
                displayJobStatus.display_position = displayJobStatus.position + 1;
                displayJobStatus.position_description = `${displayJobStatus.position} job${displayJobStatus.position !== 1 ? 's' : ''} ahead in queue`;
            }
        }
        
        // Display response
        // [2025-05-20T13:51:20-04:00] Display the job status response without causing layout shifts
        displayRestResponse(JSON.stringify(displayJobStatus, null, 2));
        
        // Show notification based on job status
        if (jobStatus.status === 'completed') {
            showNotification(`Job ${jobId} completed successfully`, 'success');
            addLogEntry(`Job ${jobId} status: completed`, 'success');
        } else if (jobStatus.status === 'failed') {
            showNotification(`Job ${jobId} failed: ${jobStatus.error || 'Unknown error'}`, 'error');
            addLogEntry(`Job ${jobId} status: failed - ${jobStatus.error || 'Unknown error'}`, 'error');
        } else {
            showNotification(`Job ${jobId} status: ${jobStatus.status}`, 'info');
            addLogEntry(`Job ${jobId} status: ${jobStatus.status}`, 'info');
            
            // If job is in progress, show progress information
            if (jobStatus.status === 'in_progress' && jobStatus.progress !== null) {
                const progressPercent = Math.round(jobStatus.progress * 100);
                showNotification(`Job ${jobId} progress: ${progressPercent}%`, 'info');
            }
        }
    } catch (error) {
        console.error('[2025-05-20T11:40:07-04:00] Error checking job status:', error);
        showNotification(`Error checking job status: ${error.message}`, 'error');
        addLogEntry(`Error checking job status: ${error.message}`, 'error');
        
        // Display error in response container
        // [2025-05-20T13:46:40-04:00] Show REST response container with smooth transition
        elements.restResponseContainer.style.opacity = '1';
        elements.restResponseContainer.style.height = '150px';
        elements.restResponseContainer.style.overflow = 'auto';
        elements.restResponseContainer.style.padding = '10px';
        elements.restResponse.textContent = `Error: ${error.message}`;
    } finally {
        // Reset button state
        elements.checkJobStatusBtn.disabled = false;
        elements.checkJobStatusBtn.textContent = 'Check Status';
    }
}

/**
 * [2025-05-20T11:26:44-04:00] Submit a job via REST API
 * [2025-05-20T11:34:47-04:00] Updated to support synchronous requests
 * This function sends a job submission request to the Redis hub's REST API endpoint
 */
async function submitJobViaRest() {
    try {
        // Check if REST API is enabled
        if (!state.restApi.enabled) {
            showNotification('REST API is not enabled', 'error');
            return;
        }
        
        // Get job details from form
        const jobType = elements.jobType.value;
        const priority = parseInt(elements.jobPriority.value, 10) || 0;
        
        // [2025-05-20T11:28:30-04:00] Get custom job ID if provided
        // We'll use the same input field as the WebSocket submission
        const customJobIdField = document.getElementById('message-id');
        const messageId = customJobIdField && customJobIdField.value ? customJobIdField.value.trim() : null;
        
        // Parse payload JSON
        let payload;
        try {
            payload = JSON.parse(elements.jobPayload.value);
        } catch (error) {
            showNotification('Invalid JSON payload', 'error');
            return;
        }
        
        // Prepare request data
        const requestData = {
            job_type: jobType,
            payload: payload,
            priority: priority,
            // [2025-05-20T11:34:47-04:00] Added synchronous request support
            wait: state.restApi.synchronous,
            timeout: state.restApi.timeout
        };
        
        // Add message ID if provided
        if (messageId) {
            requestData.job_id = messageId;
        }
        
        // Show loading state
        elements.submitJobRestBtn.disabled = true;
        elements.submitJobRestBtn.textContent = state.restApi.synchronous ? 'Processing...' : 'Submitting...';
        
        // Make the REST API request
        const response = await fetch(state.restApi.url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        });
        
        // Parse response
        const responseData = await response.json();
        
        // Display response
        // [2025-05-20T13:46:40-04:00] Show REST response container with smooth transition
        elements.restResponseContainer.style.opacity = '1';
        elements.restResponseContainer.style.height = '150px';
        elements.restResponseContainer.style.overflow = 'auto';
        elements.restResponseContainer.style.padding = '10px';
        elements.restResponse.textContent = JSON.stringify(responseData, null, 2);
        
        // Show notification
        if (response.ok) {
            if (state.restApi.synchronous) {
                // For synchronous requests, we get back the full job status
                const status = responseData.status;
                const jobId = responseData.job_id;
                
                if (status === 'completed') {
                    showNotification(`Job completed successfully: ${jobId}`, 'success');
                    addLogEntry(`Job completed via synchronous REST API: ${jobId}`, 'success');
                } else if (status === 'failed') {
                    showNotification(`Job failed: ${jobId}`, 'error');
                    addLogEntry(`Job failed via synchronous REST API: ${jobId} - ${responseData.error || 'Unknown error'}`, 'error');
                } else {
                    showNotification(`Job ${status}: ${jobId}`, 'info');
                    addLogEntry(`Job ${status} via synchronous REST API: ${jobId}`, 'info');
                }
            } else {
                // For asynchronous requests, we just get a job ID
                const jobId = responseData.job_id;
                
                // [2025-05-25T09:20:00-04:00] Store job data in state for access in job details modal
                // This ensures the payload is available when viewing job details
                if (jobId) {
                    // Store the job in state
                    state.jobs[jobId] = {
                        id: jobId,
                        status: 'pending',
                        job_type: jobType,
                        priority: priority,
                        // Store the payload data
                        payload: payload,
                        createdAt: Date.now(),
                        updated_at: Date.now(),
                        source_update: 'rest_api_submit'
                    };
                    console.log(`[2025-05-25T09:20:00-04:00] Created job state for ${jobId} from REST API submission with payload:`, payload);
                }
                
                // [2025-05-20T13:27:02-04:00] Auto-fill the job status ID field
                if (elements.jobStatusId && jobId) {
                    elements.jobStatusId.value = jobId;
                    console.log(`[2025-05-20T13:27:02-04:00] Auto-filled job status ID field with: ${jobId}`);
                    addLogEntry(`Auto-filled job status ID field with: ${jobId}`, 'info');
                    
                    // Add visual highlight effect to the job status ID field
                    elements.jobStatusId.classList.add('highlight-field');
                    
                    // Remove highlight after 3 seconds
                    setTimeout(() => {
                        elements.jobStatusId.classList.remove('highlight-field');
                    }, 3000);
                    
                    // [2025-05-20T13:46:40-04:00] Removed auto-scrolling to prevent UI from moving down
                    // Instead, just highlight the check status button to draw attention
                    const checkStatusBtn = elements.checkJobStatusBtn;
                    if (checkStatusBtn) {
                        checkStatusBtn.classList.add('highlight-button');
                        setTimeout(() => {
                            checkStatusBtn.classList.remove('highlight-button');
                        }, 3000);
                    }
                    
                    // Also highlight the check status button to encourage clicking it
                    if (elements.checkJobStatusBtn) {
                        elements.checkJobStatusBtn.classList.add('highlight-button');
                        setTimeout(() => {
                            elements.checkJobStatusBtn.classList.remove('highlight-button');
                        }, 3000);
                    }
                }
                
                showNotification(`Job submitted via REST API: ${jobId}`, 'success');
                addLogEntry(`Job submitted via REST API: ${jobId}`, 'success');
            }
        } else {
            showNotification(`REST API Error: ${responseData.detail || 'Unknown error'}`, 'error');
            addLogEntry(`REST API Error: ${responseData.detail || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        console.error('[2025-05-20T11:34:47-04:00] Error submitting job via REST:', error);
        showNotification(`Error: ${error.message}`, 'error');
        addLogEntry(`Error submitting job via REST: ${error.message}`, 'error');
        
        // Display error in response container
        // [2025-05-20T13:46:40-04:00] Show REST response container with smooth transition
        elements.restResponseContainer.style.opacity = '1';
        elements.restResponseContainer.style.height = '150px';
        elements.restResponseContainer.style.overflow = 'auto';
        elements.restResponseContainer.style.padding = '10px';
        elements.restResponse.textContent = `Error: ${error.message}`;
    } finally {
        // Reset button state
        elements.submitJobRestBtn.disabled = false;
        elements.submitJobRestBtn.textContent = 'Submit Job: REST';
    }
}

/**
 * Submit a job to Redis using the client connection
 * @param {string} [customMessageId] - Optional custom message ID to use
 * @returns {Promise<string|null>} - The message ID of the submitted job, or null if submission failed
 */
async function submitJob(customMessageId = null) {
    // Debug logging
    
    if (!state.clientConnected) {
        addLogEntry('Cannot submit job: Client connection not active', 'error');
        return;
    }
    
    try {
        // Get job details from form
        const jobType = elements.jobType.value;
        // 2025-04-09 15:01: Fix job ID generation to ensure only string values are used
        // If a custom message ID is provided and it's a string, use it; otherwise get from the form
        let userMessageId = (typeof customMessageId === 'string') ? customMessageId : document.getElementById('message-id').value.trim();
        // Generate a UUID and concatenate with the user's message ID
        const uuid = generateUUID();
        const messageId = userMessageId ? `${userMessageId}-${uuid}` : `job-submit-${Date.now()}`;
        const priority = parseInt(elements.jobPriority.value, 10);
        
        let payload;
        
        try {
            // Parse payload as JSON
            payload = JSON.parse(elements.jobPayload.value);
        } catch (error) {
            addLogEntry(`Invalid JSON payload: ${error.message}`, 'error');
            return;
        }
        
        // Create submit job message using Messages class
        const message = Messages.createSubmitJobMessage(jobType, priority, payload);
        
        // Use the concatenated message_id (user input + UUID)
        message.message_id = messageId;
        
        // Add debug log for message_id usage
        addLogEntry(`Using message_id: ${messageId}`, 'info');
        if (userMessageId) {
            addLogEntry(`(Based on user input: ${userMessageId})`, 'info');
        }
        
        // Debug logging
        console.log('Submitting job:', message);
        
        // Send message through the client connection
        state.clientSocket.send(JSON.stringify(message));
        
        // Store the request in state for tracking
        if (!state.pendingRequests) {
            state.pendingRequests = {};
        }
        
        state.pendingRequests[message.message_id] = {
            type: message.type,
            timestamp: message.timestamp,
            status: 'pending',
            jobType: jobType,
            priority: priority
        };
        
        // Update UI to give feedback
        const activeButton = document.querySelector('.priority-btn.active');
        if (activeButton && !customMessageId) {
            // Flash the button to indicate submission (only for manual submissions)
            activeButton.classList.add('btn-flash');
            setTimeout(() => {
                activeButton.classList.remove('btn-flash');
            }, 500);
        }
        
        if (!customMessageId) {
            addLogEntry(`Submitted job of type '${jobType}' with priority ${priority}`, 'success');
        }
        
        // Return the message ID for tracking
        return messageId;
    } catch (error) {
        console.error('Job submission error:', error);
        if (!customMessageId) {
            addLogEntry(`Error submitting job: ${error.message}`, 'error');
        }
        return null;
    }
}

/**
 * 2025-04-09 13:41: Batch submit multiple jobs to test race conditions
 * @param {Event} event - The click event
 */
async function batchSubmitJobs(event) {
    if (event) event.preventDefault();
    
    if (!state.clientConnected) {
        addLogEntry('Cannot submit batch: Client connection not active', 'error');
        return;
    }
    
    // Get the number of jobs to submit
    const batchCount = parseInt(document.getElementById('batch-count').value, 10);
    if (isNaN(batchCount) || batchCount < 1 || batchCount > 20) {
        addLogEntry('Invalid batch count. Please enter a number between 1 and 20.', 'error');
        return;
    }
    
    const batchResults = document.getElementById('batch-results');
    batchResults.innerHTML = `<div>Submitting ${batchCount} jobs simultaneously...</div>`;
    
    // Create a base message ID that will be made unique for each job
    const baseMessageId = `batch-test-${Date.now()}`;
    
    // Create an array of promises for all job submissions
    const submissionPromises = [];
    const messageIds = [];
    
    // Submit all jobs nearly simultaneously
    for (let i = 0; i < batchCount; i++) {
        const uniqueMessageId = `${baseMessageId}-job-${i+1}`;
        messageIds.push(uniqueMessageId);
        submissionPromises.push(submitJob(uniqueMessageId));
    }
    
    // Wait for all submissions to complete
    const results = await Promise.all(submissionPromises);
    
    // Count successful submissions
    const successCount = results.filter(Boolean).length;
    
    // Display results
    let resultHTML = `<div class="batch-result-summary">Completed ${successCount}/${batchCount} submissions</div>`;
    resultHTML += `<div class="batch-result-detail">Message IDs: ${messageIds.join(', ')}</div>`;
    
    batchResults.innerHTML = resultHTML;
    addLogEntry(`Batch submission complete: ${successCount}/${batchCount} jobs submitted successfully`, 'info');
}

/**
 * Request system statistics
 * [2025-05-20T11:23:31-04:00] Updated to use automatic stats broadcasts
 */
function requestStats() {
    // Check if monitor is connected
    if (!state.monitorConnected) {
        addLogEntry('Cannot request stats: Monitor not connected', 'error');
        return;
    }
    
    // Log the request
    addLogEntry('Waiting for next automatic stats broadcast...', 'info');
    
    // We don't need to send any message - the server automatically sends stats_broadcast messages
    // The handleStatsBroadcast function will process these messages when they arrive
    
    // Add a visual indicator that we're waiting for stats
    const statsButton = document.getElementById('request-stats-btn');
    if (statsButton) {
        const originalText = statsButton.textContent;
        statsButton.textContent = 'Waiting for stats...';
        statsButton.disabled = true;
        
        // Re-enable the button after 3 seconds
        setTimeout(() => {
            statsButton.textContent = originalText;
            statsButton.disabled = false;
        }, 3000);
    }
}

/**
 * [2025-05-19T17:51:00-04:00] Collect all supported job types from connected workers
 * @returns {string[]} Array of unique job types supported by connected workers
 */
function collectSupportedJobTypes() {
    const jobTypes = new Set();
    
    // Default job type
    jobTypes.add('simulation');
    
    // Collect job types from all workers
    Object.values(state.workers).forEach(worker => {
        // Check different possible locations for supported job types
        if (worker.capabilities && Array.isArray(worker.capabilities.supported_job_types)) {
            worker.capabilities.supported_job_types.forEach(type => jobTypes.add(type));
        } else if (Array.isArray(worker.supported_job_types)) {
            worker.supported_job_types.forEach(type => jobTypes.add(type));
        }
    });
    
    return Array.from(jobTypes).sort();
}

/**
 * [2025-05-19T17:51:00-04:00] Update the job type dropdown with options based on connected workers
 */
function updateJobTypeDropdown() {
    // [2025-05-24T12:34:30-04:00] Changed from jobTypeDropdown to jobType for consistency
    const dropdown = elements.jobType;
    if (!dropdown) return;
    
    // Save current selection if any
    const currentSelection = dropdown.value;
    
    // Clear existing options
    dropdown.innerHTML = '';
    
    // Get all supported job types
    const jobTypes = collectSupportedJobTypes();
    
    // Add options to dropdown
    jobTypes.forEach(type => {
        const option = document.createElement('option');
        option.value = type;
        option.textContent = type;
        dropdown.appendChild(option);
    });
    
    // Restore previous selection if it exists in the new options
    if (jobTypes.includes(currentSelection)) {
        dropdown.value = currentSelection;
    } else if (jobTypes.length > 0) {
        // Set to first option if previous selection doesn't exist
        dropdown.value = jobTypes[0];
        // Update payload for the new selection
        updateJobPayload(jobTypes[0]);
    }
    
    console.log(`[2025-05-19T17:51:00-04:00] Updated job type dropdown with ${jobTypes.length} options`);
}

/**
 * [2025-05-19T17:54:00-04:00] Update the job payload based on the selected job type
 * @param {string} jobType - The selected job type
 */
function updateJobPayload(jobType) {
    const payloadTextarea = elements.jobPayload;
    if (!payloadTextarea) return;
    
    // Get the default payload for this job type
    const defaultPayload = DEFAULT_PAYLOADS[jobType] || DEFAULT_PAYLOADS['simulation'];
    
    // Update the payload textarea
    payloadTextarea.value = defaultPayload;
    
    console.log(`[2025-05-19T17:54:00-04:00] Updated job payload for job type: ${jobType}`);
}

/**
 * Update the UI with current state
 */
function updateUI() {
    // [2025-04-06 18:50] Improved job count display logic - removed completed jobs count
    // Get all jobs and categorize them by status
    const allJobs = Object.values(state.jobs);
    
    // [2025-04-06 20:03] Improved job filtering to prevent undefined job IDs
    // First filter out any invalid jobs (those without an ID)
    const validJobs = allJobs.filter(job => job.id !== undefined && job.id !== null);
    
    // Then filter by status for accurate display
    const queuedJobs = validJobs.filter(job => job.status === 'pending');
    
    // 2025-04-17-20:10 - Fixed job categorization to properly handle completed jobs
    // Check for jobs with 100% progress and completed status or explicitly marked as completed
    const completedJobs = validJobs.filter(job => job.status === 'completed');
    
    // Jobs are only active if they're explicitly marked as active/processing AND not at 100% progress
    const activeJobs = validJobs.filter(job => 
        (job.status === 'active' || job.status === 'processing') && 
        // If a job has 100% progress and a completedAt timestamp, treat it as completed
        !(job.progress === 100 && job.completedAt)
    );
    
    // Move jobs with 100% progress to completed if they're still marked as active/processing
    validJobs.forEach(job => {
        if ((job.status === 'active' || job.status === 'processing') && job.progress === 100) {
            // If the job has 100% progress but is still marked as active, update it to completed
            console.log(`[DEBUG] Moving job ${job.id} from active to completed (100% progress)`); 
            job.status = 'completed';
            job.completedAt = job.completedAt || Date.now();
        }
    });
    
    const failedJobs = validJobs.filter(job => job.status === 'failed');
    
    // Log job counts by status for debugging
    console.log(`[2025-04-17-20:10] Job counts by status: queued=${queuedJobs.length}, active=${activeJobs.length}, completed=${completedJobs.length}, failed=${failedJobs.length}`);
    
    // Update UI with accurate counts
    elements.workersCount.textContent = state.stats.totalWorkers;
    elements.clientsCount.textContent = state.stats.totalClients;
    elements.queuedJobsCount.textContent = queuedJobs.length;
    elements.activeJobsCount.textContent = activeJobs.length;
    
    // [2025-04-06 19:00] Update workers display - using cards instead of table
    const workers = Object.values(state.workers);
    elements.workersContainer.innerHTML = '';
    
    if (workers.length > 0) {
        // Show workers container, hide no workers message
        elements.workersContainer.classList.remove('hidden');
        elements.noWorkersMessage.classList.add('hidden');
        
        // Process each worker
        workers.forEach(worker => {
            // Create worker card
            const workerCard = document.createElement('div');
            workerCard.className = 'worker-card';
            workerCard.id = `worker-card-${worker.id}`;
            
            // Format status class
            let statusClass = 'status-idle';
            if (worker.status === 'active' || worker.status === 'busy') statusClass = 'status-active';
            if (worker.status === 'error' || worker.status === 'out_of_service') statusClass = 'status-error';
            
            // Format accepting jobs indicator
            const acceptingJobsClass = worker.is_accepting_jobs ? 'status-active' : 'status-error';
            const acceptingJobsText = worker.is_accepting_jobs ? 'Yes' : 'No';
            
            // Format capabilities
            const capabilitiesText = worker.capabilities && worker.capabilities.supported_job_types ? 
                JSON.stringify(worker.capabilities.supported_job_types) : 'None';
            
            // [2025-04-06 19:08] Enhanced job display for workers
            // [2025-04-06 19:24] Enhanced job-worker association to handle property name differences
            console.log(`[DEBUG] Worker ${worker.id} current_job_id:`, worker.current_job_id);
            
            // Normalize job properties to handle both camelCase and snake_case
            Object.values(state.jobs).forEach(job => {
                // Ensure worker_id is set if workerId exists
                if (!job.worker_id && job.workerId) {
                    job.worker_id = job.workerId;
                }
                
                // Ensure consistent status property
                if (!job.status && job.jobStatus) {
                    job.status = job.jobStatus;
                }
                
                // Ensure job has an id property
                if (!job.id && job.jobId) {
                    job.id = job.jobId;
                }
            });
            
            // [2025-04-06 19:26] Improved current job handling to prevent UI jumping
            let currentJob = null;
            
            // First check if worker has a current_job_id
            if (worker.current_job_id && state.jobs[worker.current_job_id]) {
                currentJob = state.jobs[worker.current_job_id];
                console.log(`[DEBUG] Found current job by worker.current_job_id:`, currentJob);
            } 
            // If no current job found by ID, look for any job assigned to this worker with active status
            else {
                const activeJobsForWorker = Object.values(state.jobs).filter(job => {
                    const jobWorkerId = job.worker_id || job.workerId;
                    const jobStatus = job.status || job.jobStatus;
                    return jobWorkerId === worker.id && 
                           (jobStatus === 'active' || jobStatus === 'processing');
                });
                
                if (activeJobsForWorker.length > 0) {
                    // Use the job with the most recent update
                    currentJob = activeJobsForWorker.sort((a, b) => {
                        const aTime = a.updated_at || a.updatedAt || 0;
                        const bTime = b.updated_at || b.updatedAt || 0;
                        return bTime - aTime;
                    })[0];
                    
                    console.log(`[DEBUG] Found current job by active status:`, currentJob);
                    
                    // Update worker's current_job_id to match this job
                    if (currentJob) {
                        worker.current_job_id = currentJob.id || currentJob.jobId;
                        console.log(`[DEBUG] Updated worker.current_job_id to ${worker.current_job_id}`);
                    }
                }
            }
            
            if (currentJob) {
                // Ensure the job is linked to this worker
                currentJob.worker_id = worker.id;
                
                // 2025-04-17-20:13 - Don't override completed or failed job statuses
                // Only set status to processing if it's not already in a terminal state
                if (currentJob.status !== 'processing' && 
                    currentJob.status !== 'active' && 
                    currentJob.status !== 'completed' && 
                    currentJob.status !== 'failed') {
                    currentJob.status = 'processing';
                }
                
                // If job is completed or failed, clear it from the worker's current_job_id
                if (currentJob.status === 'completed' || currentJob.status === 'failed') {
                    console.log(`[DEBUG] Clearing worker ${worker.id} current_job_id as job ${currentJob.id} is in terminal state: ${currentJob.status}`);
                    worker.current_job_id = null;
                }
                console.log(`[DEBUG] Current job for worker ${worker.id}:`, {
                    id: currentJob.id || currentJob.jobId,
                    status: currentJob.status,
                    progress: currentJob.progress || 0
                });
            } else {
                console.log(`[DEBUG] No current job found for worker ${worker.id}`);
            }
            
            // [2025-04-06 20:00] Calculate estimated completion time for current job
            let estimatedCompletion = '';
            if (currentJob && (currentJob.status === 'processing' || currentJob.status === 'active') && currentJob.progress > 0) {
                estimatedCompletion = estimateCompletionTime(currentJob);
            }
            
            // Log all jobs to see what's available
            console.log(`[DEBUG] All jobs in state:`, Object.keys(state.jobs).length);
            
            // Find active jobs for this worker (those with status 'active' or 'processing')
            const activeJobs = Object.values(state.jobs)
                .filter(job => {
                    // Check both worker_id and workerId properties
                    const jobWorkerId = job.worker_id || job.workerId;
                    const jobStatus = job.status || job.jobStatus;
                    
                    const isMatch = jobWorkerId === worker.id && 
                                    (jobStatus === 'active' || jobStatus === 'processing');
                    
                    // Log each active job match attempt
                    if (jobWorkerId === worker.id) {
                        console.log(`[DEBUG] Job ${job.id || job.jobId} for worker ${worker.id}: status=${jobStatus}, match=${isMatch}`);
                    }
                    return isMatch;
                });
            
            console.log(`[DEBUG] Found ${activeJobs.length} active jobs for worker ${worker.id}`);
                
            // [2025-04-06 19:44] Removed recent jobs collection as we now have a dedicated Finished Jobs table
            // Only use active jobs for the worker card
            const workerJobs = activeJobs;
            
            // [2025-04-06 19:51] Create the worker card HTML with compact design and placeholders
            workerCard.innerHTML = `
                <div class="worker-header">
                    <div class="worker-title">${worker.id}</div>
                    <div><span class="status ${statusClass}">${worker.status || 'Connected'}</span></div>
                </div>
                
                <!-- [2025-04-06 19:59] Simplified worker info to show only essential information -->
                <div class="worker-info">
                    <div class="worker-info-item">
                        <div class="worker-info-label">Jobs Processed</div>
                        <div class="worker-info-value">${worker.jobsProcessed || 0}</div>
                    </div>
                    <div class="worker-info-item">
                        <div class="worker-info-label">Job Types</div>
                        <div class="worker-info-value">${worker.supported_job_types ? worker.supported_job_types.join(', ') : 
                            (worker.capabilities && worker.capabilities.supported_job_types ? 
                            worker.capabilities.supported_job_types.join(', ') : 'Unknown')}</div>
                    </div>
                </div>
                
                <div class="current-job-wrapper">
                    ${currentJob ? `
                    <div class="current-job-section">
                        <div class="current-job-header">
                            <div>
                                <strong>Current Job</strong>
                                <span class="job-type-badge">${currentJob.job_type || currentJob.type || 'Unknown'}</span>
                            </div>
                            <div class="job-times">
                                <div class="job-time">Created: ${formatDateTime(currentJob.createdAt || currentJob.created_at)}</div>
                                <div class="job-time">Started: ${formatDateTime(currentJob.processingStartedAt) || 'Pending'}</div>
                            </div>
                        </div>
                        
                        <div class="current-job-progress">
                            <div class="progress-label">Progress: ${currentJob.progress || 0}%</div>
                            <div class="progress-container">
                                <div class="progress-bar" style="width: ${currentJob.progress || 0}%;"></div>
                            </div>
                            <div class="current-job-meta">
                                <div>ID: ${currentJob.id.substring(0, 8)}...</div>
                                <div class="estimated-completion">
                                    ${estimatedCompletion ? `Est. completion: ${estimatedCompletion}` : ''}
                                </div>
                            </div>
                        </div>
                        
                        <div class="job-payload-section">
                            <details>
                                <summary>Payload Preview</summary>
                                <pre class="job-payload-preview">${formatPayload(currentJob.payload)}</pre>
                            </details>
                        </div>
                    </div>
                    ` : `
                    <div class="no-job-placeholder">
                        <div class="no-job-message">Waiting for job...</div>
                    </div>
                    `}
                </div>
                
                <style>
                    /* [2025-04-06 19:51] Compact styling for worker cards with fixed dimensions */
                    .worker-header {
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        margin-bottom: 8px;
                        padding-bottom: 4px;
                        border-bottom: 1px solid #eee;
                    }
                    .worker-title {
                        font-weight: bold;
                        font-size: 0.9rem;
                    }
                    .worker-info {
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
                        gap: 8px;
                        margin-bottom: 8px;
                    }
                    .worker-info-item {
                        display: flex;
                        flex-direction: column;
                    }
                    .worker-info-label {
                        font-size: 0.65rem;
                        color: #666;
                        text-transform: uppercase;
                    }
                    .worker-info-value {
                        font-size: 0.8rem;
                    }
                    .current-job-wrapper {
                        min-height: 100px; /* Fixed height to prevent UI jumping */
                    }
                    .current-job-section {
                        background-color: #f0f8ff;
                        border-radius: 4px;
                        padding: 8px;
                        border-left: 3px solid #4285f4;
                    }
                    .current-job-header {
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        margin-bottom: 6px;
                        font-size: 0.8rem;
                    }
                    .job-type-badge {
                        background-color: #e9ecef;
                        border-radius: 3px;
                        padding: 1px 4px;
                        font-size: 0.65rem;
                        margin-left: 4px;
                    }
                    .job-times {
                        display: flex;
                        flex-direction: column;
                        align-items: flex-end;
                    }
                    .job-time {
                        font-size: 0.7rem;
                        color: #666;
                        margin-bottom: 2px;
                    }
                    .current-job-progress {
                        margin-bottom: 6px;
                    }
                    .progress-label {
                        font-size: 0.75rem;
                        margin-bottom: 2px;
                    }
                    .progress-container {
                        height: 8px;
                        background-color: #e9ecef;
                        border-radius: 4px;
                        overflow: hidden;
                    }
                    .progress-bar {
                        height: 100%;
                        background-color: #4285f4;
                        border-radius: 4px;
                    }
                    .estimated-completion {
                        font-size: 0.65rem;
                        color: #666;
                        margin-top: 2px;
                        text-align: right;
                    }
                    .current-job-meta {
                        display: flex;
                        justify-content: space-between;
                        font-size: 0.7rem;
                        margin-top: 4px;
                    }
                    .job-payload-section {
                        margin-top: 6px;
                        border-top: 1px solid #eee;
                        padding-top: 6px;
                    }
                    .job-payload-section summary {
                        cursor: pointer;
                        font-size: 0.75rem;
                        color: #555;
                    }
                    .job-payload-preview {
                        background-color: #f5f5f5;
                        padding: 6px;
                        border-radius: 3px;
                        font-size: 0.65rem;
                        max-height: 80px;
                        overflow-y: auto;
                        margin: 4px 0 0 0;
                        white-space: pre-wrap;
                    }
                    .no-job-placeholder {
                        min-height: 100px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        background-color: #f9f9f9;
                        border-radius: 4px;
                        border: 1px dashed #ddd;
                    }
                    .no-job-message {
                        font-size: 0.8rem;
                        color: #888;
                        font-style: italic;
                    }
                </style>
            `;
            
            // [2025-04-06 19:49] Removed job rows code as we no longer display active jobs in worker cards
            // Add the worker card to the container
            elements.workersContainer.appendChild(workerCard);
        });
    } else {
        // No workers connected
        elements.workersContainer.classList.add('hidden');
        elements.noWorkersMessage.classList.remove('hidden');
    }
    
    // [2025-04-06 19:00] Update jobs table - only show queued jobs
    // Only display queued (pending) jobs in the job queue
    elements.jobsTableBody.innerHTML = '';
    
    if (queuedJobs.length > 0) {
        elements.jobsTableContainer.classList.remove('hidden');
        elements.noJobsMessage.classList.add('hidden');
        
        // Sort jobs by priority (highest first) and then by created_at (oldest first)
        queuedJobs.sort((a, b) => {
            // First sort by priority (higher priority first)
            const aPriority = parseInt(a.priority || 0);
            const bPriority = parseInt(b.priority || 0);
            
            if (bPriority !== aPriority) {
                return bPriority - aPriority;
            }
            
            // If same priority, sort by creation time (oldest first)
            const aCreatedAt = a.created_at || 0;
            const bCreatedAt = b.created_at || 0;
            return aCreatedAt - bCreatedAt;
        });
        
        // Log once before processing jobs
        console.log(`[2025-04-06 19:00] Displaying ${queuedJobs.length} queued jobs`);
        
        queuedJobs.forEach(job => {
            const row = document.createElement('tr');
            
            // Format status class
            const statusClass = 'status-queued';
            const displayStatus = 'queued';
            
            // Force priority to be a number
            const displayPriority = parseInt(job.priority || 0);
            
            // [2025-04-06 20:07] Format created time as absolute datetime instead of relative time
            // This prevents the display from constantly changing and provides consistent time representation
            const createdAtStr = formatDateTime(job.created_at ? new Date(job.created_at * 1000) : null);
            
            // Get failure count for this job
            // [2025-05-19T17:58:00-04:00] Added failure count tracking
            let failureCount = 0;
            if (state.worker_failed_jobs) {
                // Count how many workers have failed this job
                Object.values(state.worker_failed_jobs).forEach(failedJobs => {
                    if (failedJobs.includes(job.id)) {
                        failureCount++;
                    }
                });
            }
            
            // Create the job row
            // [2025-04-06 20:40] Added client_id column
            // 2025-04-09 13:53: Modified to display full job ID without truncation
            // 2025-04-26 22:59: Added cancel button to each job row
            // [2025-05-19T17:58:00-04:00] Added failures column
            // [2025-05-19T18:03:00-04:00] Added force retry button
            row.innerHTML = `
                <td class="job-id-cell" title="${job.id}">${job.id}</td>
                <td>${job.client_id || 'N/A'}</td>
                <td>${job.job_type || job.type || ''}</td>
                <td><span class="status ${statusClass}">${displayStatus}</span></td>
                <td>${displayPriority}</td>
                <td>
                    ${job.position !== undefined ? 
                        (job.position === 0 ? 
                            '<span class="position-next">Next up</span>' : 
                            `<span class="position-waiting">${job.position} job${job.position !== 1 ? 's' : ''} ahead</span>`
                        ) : 'N/A'}
                </td>
                <td>${createdAtStr}</td>
                <td>${failureCount > 0 ? `<span class="failure-count">${failureCount}</span>` : '0'}</td>
                <td class="job-actions">
                    <!-- [2025-05-24T12:42:00-04:00] Improved button layout with horizontal flex container -->
                    <div class="action-buttons-container">
                        <button class="btn-cancel" onclick="cancelJob('${job.id}')">Cancel</button>
                        ${failureCount > 0 ? `<button class="btn-force-retry" onclick="forceRetryJob('${job.id}')">Force Retry</button>` : ''}
                        <!-- [2025-05-25T09:35:00-04:00] Changed to use data attributes for event delegation -->
                        <button class="action-btn" data-action="view-details" data-job-id="${job.id}" title="View details">⋯</button>
                    </div>
                </td>
            `;
            
            elements.jobsTableBody.appendChild(row);
        });
    } else {
        // No queued jobs
        elements.jobsTableContainer.classList.add('hidden');
        elements.noJobsMessage.classList.remove('hidden');
    }
    
    // [2025-04-06 19:40] Update finished jobs table - show completed, failed, and cancelled jobs
    elements.finishedJobsTableBody.innerHTML = '';
    
    // [2025-04-06 20:03] Find all finished jobs (completed, failed, or cancelled)
    // Only include jobs with valid IDs to prevent undefined job IDs in the table
    const finishedJobs = validJobs.filter(job => 
        job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled'
    );
    
    if (finishedJobs.length > 0) {
        elements.finishedJobsContainer.classList.remove('hidden');
        elements.noFinishedJobsMessage.classList.add('hidden');
        
        // Sort by most recently finished first
        finishedJobs.sort((a, b) => {
            // Get the timestamp when the job was finished
            const aTime = a.completedAt || a.failedAt || a.cancelledAt || a.updated_at || 0;
            const bTime = b.completedAt || b.failedAt || b.cancelledAt || b.updated_at || 0;
            return bTime - aTime; // Most recent first
        });
        
        // Log once before processing jobs
        console.log(`[2025-04-06 19:40] Displaying ${finishedJobs.length} finished jobs`);
        
        // Only show the most recent 20 finished jobs to avoid cluttering the UI
        const recentFinishedJobs = finishedJobs.slice(0, 20);
        
        recentFinishedJobs.forEach(job => {
            const row = document.createElement('tr');
            
            // [2025-04-06 19:40] Enhanced status formatting with more detailed status display
            let statusClass = 'status-idle';
            let statusText = job.status;
            
            // Format status class and text for better readability
            if (job.status === 'completed') {
                statusClass = 'status-completed';
                statusText = 'Completed';
            } else if (job.status === 'failed') {
                statusClass = 'status-error';
                statusText = 'Failed';
            } else if (job.status === 'cancelled') {
                statusClass = 'status-idle'; // Use idle style for cancelled (yellow)
                statusText = 'Cancelled';
            }
            
            // Create progress bar
            const progressBar = `
                <div class="progress-container" style="height: 10px;">
                    <div class="progress-bar" style="width: ${job.progress || 0}%; height: 10px;">
                    </div>
                </div>
                <div style="font-size: 0.7rem; text-align: center;">${job.progress || 0}%</div>
            `;
            
            // Calculate job duration
            const jobDuration = formatDuration(job.createdAt || job.created_at, job);
            
            // Format start time using absolute datetime
            const startTime = formatDateTime(job.createdAt || job.created_at);
            
            // Format finished time based on job status using absolute datetime
            let finishedTime;
            if (job.status === 'completed' && job.completedAt) {
                finishedTime = formatDateTime(job.completedAt);
            } else if (job.status === 'failed' && job.failedAt) {
                finishedTime = formatDateTime(job.failedAt);
            } else if (job.status === 'cancelled' && job.cancelledAt) {
                finishedTime = formatDateTime(job.cancelledAt);
            } else {
                finishedTime = formatDateTime(job.updated_at);
            }
            
            // Create the job row with client ID and worker ID columns
            // [2025-04-06 20:40] Added client_id column
            row.innerHTML = `
                <!-- 2025-04-09 13:53: Modified to display full job ID without truncation -->
                <td class="job-id-cell" title="${job.id}">${job.id}</td>
                <td>${job.client_id || 'N/A'}</td>
                <td>${job.worker_id || job.workerId || 'N/A'}</td>
                <td>${job.job_type || job.type || ''}</td>
                <td><span class="status ${statusClass}">${statusText}</span></td>
                <td>${progressBar}</td>
                <td>${jobDuration}</td>
                <td>${startTime}</td>
                <td>${finishedTime}</td>
                <td class="job-actions">
                    ${job.status === 'failed' ? `
                        <!-- [2025-05-24T12:46:00-04:00] Changed to use onclick for consistency with other buttons -->
                        <button class="action-btn" onclick="retryJob('${job.id}')" title="Retry job">↻</button>
                        <div class="error-tooltip">
                            <button class="action-btn error-btn" title="View error">!</button>
                            <div class="tooltip-content">
                                <div class="error-message">${formatErrorMessage(job.error || 'Unknown error')}</div>
                            </div>
                        </div>
                    ` : ''}
                    <!-- [2025-05-25T09:40:00-04:00] Changed to use data attributes for event delegation -->
                    <button class="action-btn" data-action="view-details" data-job-id="${job.id}" title="View details">⋯</button>
                </td>
            `;
            
            elements.finishedJobsTableBody.appendChild(row);
        });
        
        // Add event listeners for the action buttons
        document.querySelectorAll('.retry-btn').forEach(button => {
            button.addEventListener('click', function() {
                const jobId = this.getAttribute('data-job-id');
                retryJob(jobId);
            });
        });
        
        document.querySelectorAll('.details-btn').forEach(button => {
            button.addEventListener('click', function() {
                const jobId = this.getAttribute('data-job-id');
                showJobDetails(jobId);
            });
        });
    } else {
        // No finished jobs
        elements.finishedJobsContainer.classList.add('hidden');
        elements.noFinishedJobsMessage.classList.remove('hidden');
    }
    
    // [2025-05-19T17:55:00-04:00] Update job type dropdown with options from connected workers
    updateJobTypeDropdown();
}

/**
 * Add a log entry to the logs panel
 */
function addLogEntry(message, type = 'info') {
    const logEntry = document.createElement('div');
    logEntry.className = `log-entry log-${type}`;
    
    const timestamp = new Date().toLocaleTimeString();
    
    logEntry.innerHTML = `
        <span class="log-time">[${timestamp}]</span>
        <span class="log-message">${message}</span>
    `;
    
    elements.logs.appendChild(logEntry);
    elements.logs.scrollTop = elements.logs.scrollHeight;
}

/**
 * Format a date as a relative time string
 */
function formatRelativeTime(date) {
    if (!date) return 'N/A';
    
    // Convert to Date object if it's a string
    if (typeof date === 'string') {
        date = new Date(date);
    }
    
    const now = new Date();
    const diffInSeconds = Math.floor((now - date) / 1000);
    
    if (diffInSeconds < 60) {
        return `${diffInSeconds} seconds ago`;
    } else if (diffInSeconds < 3600) {
        const minutes = Math.floor(diffInSeconds / 60);
        return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
    } else if (diffInSeconds < 86400) {
        const hours = Math.floor(diffInSeconds / 3600);
        return `${hours} hour${hours > 1 ? 's' : ''} ago`;
    } else {
        const days = Math.floor(diffInSeconds / 86400);
        return `${days} day${days > 1 ? 's' : ''} ago`;
    }
}

/**
 * [2025-04-06 19:56] Format memory size to human-readable format
 * @param {number|string} memory - Memory size in bytes or formatted string
 * @returns {string} Formatted memory string
 */
function formatMemory(memory) {
    // If already a formatted string (e.g., "16GB")
    if (typeof memory === 'string') {
        if (memory.endsWith('GB') || memory.endsWith('MB') || memory.endsWith('KB')) {
            return memory;
        }
        // Try to parse as number
        memory = parseInt(memory, 10);
    }
    
    if (memory === undefined || memory === null || isNaN(memory)) {
        return 'N/A';
    }
    
    // Format based on size
    if (memory < 1024) return `${memory} B`;
    if (memory < 1024 * 1024) return `${(memory / 1024).toFixed(1)} KB`;
    if (memory < 1024 * 1024 * 1024) return `${(memory / (1024 * 1024)).toFixed(1)} MB`;
    return `${(memory / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

/**
 * [2025-04-06 19:09] Format the duration of a job from start time to now or completion
 * @param {Date|string} startDate - The start date of the job
 * @param {Object} job - Optional job object with duration or completion time
 * @returns {string} - Formatted duration string
 * [2025-04-06 19:35] Updated to use job's stored duration or completion time when available
 */
function formatDuration(startDate, job) {
    if (!startDate) return 'N/A';
    
    let diffInSeconds;
    
    // If job has a stored duration, use that (it's already in seconds)
    if (job && job.duration) {
        diffInSeconds = job.duration;
        console.log(`[DEBUG] Using stored duration for job: ${diffInSeconds}s`);
    }
    // If job has a completion time, calculate duration from start to completion
    else if (job && (job.completedAt || job.completed_at)) {
        const endTime = job.completedAt || job.completed_at;
        let endDate = endTime;
        
        // Convert to Date object if it's a string or number
        if (typeof endTime === 'string') {
            endDate = new Date(endTime);
        } else if (typeof endTime === 'number') {
            endDate = new Date(endTime);
        }
        
        // Convert start date to Date object if it's a string or number
        let startDateObj = startDate;
        if (typeof startDate === 'string') {
            startDateObj = new Date(startDate);
        } else if (typeof startDate === 'number') {
            startDateObj = new Date(startDate);
        }
        
        diffInSeconds = Math.floor((endDate - startDateObj) / 1000);
        console.log(`[DEBUG] Calculated duration from start to completion: ${diffInSeconds}s`);
    }
    // Otherwise, calculate duration from start to now (for active jobs)
    else {
        // Convert to Date object if it's a string or number
        let startDateObj = startDate;
        if (typeof startDate === 'string') {
            startDateObj = new Date(startDate);
        } else if (typeof startDate === 'number') {
            startDateObj = new Date(startDate);
        }
        
        const now = new Date();
        diffInSeconds = Math.floor((now - startDateObj) / 1000);
        console.log(`[DEBUG] Calculated duration from start to now: ${diffInSeconds}s`);
    }
    
    // Format as hours:minutes:seconds
    const hours = Math.floor(diffInSeconds / 3600);
    const minutes = Math.floor((diffInSeconds % 3600) / 60);
    const seconds = diffInSeconds % 60;
    
    if (hours > 0) {
        return `${hours}h ${minutes}m ${seconds}s`;
    } else if (minutes > 0) {
        return `${minutes}m ${seconds}s`;
    } else {
        return `${seconds}s`;
    }
}

/**
 * [2025-05-24T23:15:00-04:00] Format job payload for display
 * @param {Object} payload - The job payload
 * @returns {string} - Formatted payload string
 */
function formatPayload(payload) {
    if (!payload) return 'No payload data';
    
    try {
        // Log the payload for debugging
        console.log('[DEBUG] Formatting payload:', payload, 'Type:', typeof payload);
        
        // If payload is already a string, try to parse it as JSON for pretty printing
        if (typeof payload === 'string') {
            try {
                const parsedPayload = JSON.parse(payload);
                return JSON.stringify(parsedPayload, null, 2);
            } catch (e) {
                // If it's not valid JSON, return as is (truncated if too long)
                return payload.length > 500 ? payload.substring(0, 500) + '...' : payload;
            }
        }
        
        // If payload is an object, stringify it
        return JSON.stringify(payload, null, 2);
    } catch (e) {
        console.error('Error formatting payload:', e, payload);
        return 'Error displaying payload';
    }
}

/**
 * [2025-04-06 19:13] Format error message for display
 * @param {string} error - The error message
 * @returns {string} - Formatted error message
 */
function formatErrorMessage(error) {
    if (!error) return 'Unknown error';
    
    // If error is longer than 200 characters, truncate it
    if (typeof error === 'string' && error.length > 200) {
        return error.substring(0, 200) + '...';
    }
    
    return error;
}

/**
 * [2025-04-06 19:13] Estimate completion time based on progress and elapsed time
 * @param {Object} job - The job object
 * @returns {string} - Estimated completion time
 */
/**
 * [2025-04-06 20:10] Estimate completion time for a job
 * - Now uses processing start time instead of creation time for more accurate estimates
 * - Added tracking of when a job actually starts processing
 * - Handles different date formats and property names
 * - Includes validation to prevent unrealistic estimates
 */
function estimateCompletionTime(job) {
    // Validate job and progress data
    if (!job || job.progress === undefined || job.progress <= 0 || job.progress >= 100) {
        return 'Unknown';
    }
    
    // Get job processing start time, prioritizing processing time over creation time
    // This is critical for accurate estimates, especially for jobs that waited in queue
    const processingStartRaw = 
        job.processingStartedAt || // Use our custom tracking property first
        job.startedAt || 
        job.started_at || 
        job.processingStart;
    
    // Fall back to creation time only if processing time is not available
    const startTimeRaw = processingStartRaw || job.createdAt || job.created_at;
    if (!startTimeRaw) {
        return 'Unknown';
    }
    
    // Convert to Date object if it's a string or number
    let startTime;
    if (typeof startTimeRaw === 'number') {
        // Handle Unix timestamp in seconds
        startTime = new Date(startTimeRaw * 1000);
    } else {
        startTime = new Date(startTimeRaw);
    }
    
    // Validate the date is valid
    if (isNaN(startTime.getTime())) {
        return 'Unknown';
    }
    
    const now = new Date();
    const elapsedSeconds = Math.max(1, (now - startTime) / 1000); // Ensure at least 1 second elapsed
    
    // Calculate estimated total time based on current progress
    const progress = parseFloat(job.progress);
    const estimatedTotalSeconds = (elapsedSeconds / progress) * 100;
    
    // Calculate remaining time
    const remainingSeconds = estimatedTotalSeconds - elapsedSeconds;
    
    // Sanity check - if estimate is unreasonable, return unknown
    if (remainingSeconds < 0 || remainingSeconds > 86400 * 7) { // Cap at 1 week
        return 'Unknown';
    }
    
    // Format remaining time
    if (remainingSeconds < 60) {
        return `${Math.round(remainingSeconds)}s remaining`;
    } else if (remainingSeconds < 3600) {
        return `${Math.round(remainingSeconds / 60)}m remaining`;
    } else {
        const hours = Math.floor(remainingSeconds / 3600);
        const minutes = Math.round((remainingSeconds % 3600) / 60);
        return `${hours}h ${minutes}m remaining`;
    }
}

// Periodic stats refresh removed as we're using server push instead

/**
 * 2025-04-26 23:00 - Cancel a job
 * @param {string} jobId - The ID of the job to cancel
 */
function cancelJob(jobId) {
    // Check if client socket is connected
    if (!state.clientConnected) {
        showNotification('Cannot cancel job: Client not connected', 'error');
        return;
    }
    
    // Find the job in the state
    const job = state.jobs[jobId];
    
    if (!job) {
        showNotification(`Job ${jobId} not found`, 'error');
        return;
    }
    
    // Confirm cancellation
    if (!confirm(`Are you sure you want to cancel job ${jobId}?`)) {
        return;
    }
    
    // Create a cancel job message
    const cancelMessage = {
        type: 'cancel_job',
        job_id: jobId,
        reason: 'Manually cancelled from Redis Monitor',
        timestamp: Date.now() / 1000
    };
    
    // Send the message
    try {
        state.clientSocket.send(JSON.stringify(cancelMessage));
        showNotification(`Cancellation request sent for job ${jobId}`, 'info');
        
        // Optimistically update the job status in the UI
        job.status = 'cancelling';
        updateUI();
    } catch (error) {
        showNotification(`Error cancelling job: ${error.message}`, 'error');
        console.error('Error cancelling job:', error);
    }
}

/**
 * [2025-05-19T18:06:00-04:00] Force retry a job that has previously failed
 * This function sends a request to clear the job's failure history
 * and allow it to be assigned to any worker, even ones that previously failed it
 */
function forceRetryJob(jobId) {
    // Check if client socket is connected
    if (!state.clientConnected) {
        showNotification('Cannot force retry job: Client not connected', 'error');
        return;
    }
    
    // Find the job in the state
    const job = state.jobs[jobId];
    
    if (!job) {
        showNotification(`Job ${jobId} not found`, 'error');
        return;
    }
    
    // Confirm force retry
    if (!confirm(`Are you sure you want to force retry job ${jobId}?\n\nThis will clear the job's failure history and allow it to be assigned to any worker, even ones that previously failed it.`)) {
        return;
    }
    
    // Create a force retry job message
    const forceRetryMessage = {
        type: 'force_retry_job',
        job_id: jobId,
        timestamp: Date.now() / 1000
    };
    
    // Send the message
    try {
        state.clientSocket.send(JSON.stringify(forceRetryMessage));
        showNotification(`Force retry request sent for job ${jobId}`, 'info');
        
        // Optimistically update the UI
        updateUI();
    } catch (error) {
        showNotification(`Error forcing retry for job: ${error.message}`, 'error');
        console.error('Error forcing retry for job:', error);
    }
}

/**
 * [2025-04-06 19:15] Retry a failed job
 * @param {string} jobId - The ID of the job to retry
 */
function retryJob(jobId) {
    // Check if client socket is connected
    if (!state.clientConnected) {
        showNotification('Cannot retry job: Client not connected', 'error');
        return;
    }
    
    // Create a new job with the same parameters
    const failedJob = state.jobs[jobId];
    
    if (!failedJob) {
        showNotification(`Job ${jobId} not found`, 'error');
        return;
    }
    
    // Create a new job with the same data
    const jobData = {
        job_type: failedJob.job_type || failedJob.type,
        priority: failedJob.priority || 0,
        payload: failedJob.payload || {}
    };
    
    // Send the job data to the server
    socket.emit('submit_job', jobData);
    
    // Show notification
    showNotification(`Retrying job ${jobId.substring(0, 8)}...`, 'success');
}

/**
 * [2025-04-06 19:15] Show detailed information about a job
 * @param {string} jobId - The ID of the job to show details for
 */
function showJobDetails(jobId) {
    if (!jobId) return;
    
    const job = state.jobs[jobId];
    if (!job) {
        console.error(`Job ${jobId} not found`);
        return;
    }
    
    // [2025-05-24T12:47:00-04:00] Use elements object for modal references
    // Create modal if it doesn't exist
    let modal = elements.jobDetailsModal;
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'job-details-modal';
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal-content">
                <span class="close-button">&times;</span>
                <h2>Job Details</h2>
                <div id="job-details-content"></div>
            </div>
        `;
        document.body.appendChild(modal);
        
        // Add close button event listener
        const closeButton = modal.querySelector('.close-button');
        closeButton.addEventListener('click', function() {
            modal.style.display = 'none';
        });
        
        // Close modal when clicking outside of it
        window.addEventListener('click', function(event) {
            if (event.target === modal) {
                modal.style.display = 'none';
            }
        });
        
        // Add CSS for modal
        const style = document.createElement('style');
        style.textContent = `
            /* [2025-05-24T12:43:00-04:00] Added styles for action buttons container */
            .action-buttons-container {
                display: flex;
                flex-direction: row;
                gap: 5px;
                align-items: center;
            }
            .job-actions {
                white-space: nowrap;
            }
            .action-btn {
                cursor: pointer;
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 14px;
            }
            .action-btn:hover {
                background-color: #e0e0e0;
            }

            .modal {
                display: none;
                position: fixed;
                z-index: 1000;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0,0,0,0.5);
            }
            .modal-content {
                background-color: white;
                margin: 10% auto;
                padding: 20px;
                border-radius: 5px;
                width: 80%;
                max-width: 800px;
                max-height: 80vh;
                overflow-y: auto;
                position: relative;
            }
            .close-button {
                position: absolute;
                top: 10px;
                right: 15px;
                font-size: 24px;
                font-weight: bold;
                cursor: pointer;
            }
            .job-details-grid {
                display: grid;
                grid-template-columns: 120px 1fr;
                gap: 8px;
                margin-bottom: 20px;
            }
            .detail-row {
                display: contents;
            }
            .detail-label {
                font-weight: bold;
                color: #555;
            }
            .job-payload-full, .job-error-full {
                background-color: #f5f5f5;
                padding: 10px;
                border-radius: 4px;
                overflow-x: auto;
                font-family: monospace;
                font-size: 0.9rem;
                white-space: pre-wrap;
                max-height: 200px;
                overflow-y: auto;
            }
            .job-error-full {
                color: #ea4335;
            }
            #notification-container {
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 9999;
                display: flex;
                flex-direction: column;
                gap: 10px;
            }
            .notification {
                padding: 12px 20px;
                border-radius: 4px;
                color: white;
                box-shadow: 0 2px 5px rgba(0,0,0,0.2);
                animation: slide-in 0.3s ease-out;
            }
            .notification-success {
                background-color: #4CAF50;
            }
            .notification-error {
                background-color: #f44336;
            }
            .notification-info {
                background-color: #2196F3;
            }
            .fade-out {
                opacity: 0;
                transition: opacity 0.3s;
            }
            @keyframes slide-in {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
        `;
        document.head.appendChild(style);
    }
    
    // [2025-05-24T12:48:00-04:00] Use elements object for modal content reference
    // Update modal content
    const content = elements.jobDetailsContent || modal.querySelector('#job-details-content');
    content.innerHTML = `
        <div class="job-details-grid">
            <div class="detail-row">
                <div class="detail-label">Job ID:</div>
                <div class="detail-value">${job.id}</div>
            </div>
            <div class="detail-row">
                <div class="detail-label">Type:</div>
                <div class="detail-value">${job.job_type || job.type || 'Unknown'}</div>
            </div>
            <div class="detail-row">
                <div class="detail-label">Status:</div>
                <div class="detail-value"><span class="status ${getStatusClass(job.status)}">${job.status}</span></div>
            </div>
            <div class="detail-row">
                <div class="detail-label">Worker:</div>
                <div class="detail-value">${job.worker_id || 'None'}</div>
            </div>
            <div class="detail-row">
                <div class="detail-label">Priority:</div>
                <div class="detail-value">${job.priority || 0}</div>
            </div>
            <div class="detail-row">
                <div class="detail-label">Created:</div>
                <div class="detail-value">${formatDate(job.createdAt)}</div>
            </div>
            <div class="detail-row">
                <div class="detail-label">Updated:</div>
                <div class="detail-value">${formatDate(job.updated_at)}</div>
            </div>
            <div class="detail-row">
                <div class="detail-label">Duration:</div>
                <div class="detail-value">${formatDuration(job.createdAt || job.created_at, job)}</div>
            </div>
            ${job.progress ? `
            <div class="detail-row">
                <div class="detail-label">Progress:</div>
                <div class="detail-value">
                    <div class="progress-container">
                        <div class="progress-bar" style="width: ${job.progress}%"></div>
                    </div>
                    <div class="progress-text">${job.progress}%</div>
                </div>
            </div>
            ` : ''}
        </div>
        
        <h3>Payload</h3>
        <pre class="job-payload-full">${formatPayload(job.payload)}</pre>
        
        ${job.error ? `
        <h3>Error</h3>
        <pre class="job-error-full">${job.error}</pre>
        ` : ''}
    `;
    
    // Show modal
    modal.style.display = 'block';
}

/**
 * [2025-04-06 19:15] Get the CSS class for a job status
 * @param {string} status - The job status
 * @returns {string} - The CSS class for the status
 */
function getStatusClass(status) {
    if (!status) return 'status-idle';
    
    if (status === 'pending') return 'status-queued';
    if (status === 'processing' || status === 'active') return 'status-active';
    if (status === 'completed') return 'status-completed';
    if (status === 'failed') return 'status-error';
    
    return 'status-idle';
}

/**
 * [2025-05-24T12:50:00-04:00] Format a date as a string with robust error handling
 * @param {Date|string|number} date - The date to format
 * @returns {string} - Formatted date string
 */
function formatDate(date) {
    if (!date) return 'N/A';
    
    try {
        let dateObj;
        
        // Handle different date formats
        if (typeof date === 'number') {
            // Handle Unix timestamp (seconds since epoch)
            // If the number is small, it's likely seconds not milliseconds
            if (date < 10000000000) {
                dateObj = new Date(date * 1000);
            } else {
                dateObj = new Date(date);
            }
        } else if (typeof date === 'string') {
            dateObj = new Date(date);
        } else if (date instanceof Date) {
            dateObj = date;
        } else {
            return 'Invalid date';
        }
        
        // Validate the date is valid
        if (isNaN(dateObj.getTime())) {
            return 'Invalid date';
        }
        
        return dateObj.toLocaleDateString() + ' ' + dateObj.toLocaleTimeString();
    } catch (error) {
        console.error('Error formatting date:', error, date);
        return 'Date error';
    }
}

/**
 * [2025-05-24T12:52:00-04:00] Format a date as a datetime string (YYYY-MM-DD HH:MM:SS) with robust error handling
 * @param {Date|string|number} date - The date to format
 * @returns {string} - Formatted datetime string
 */
function formatDateTime(date) {
    if (!date) return 'N/A';
    
    try {
        let dateObj;
        
        // Handle different date formats
        if (typeof date === 'number') {
            // Handle Unix timestamp (seconds since epoch)
            // If the number is small, it's likely seconds not milliseconds
            if (date < 10000000000) {
                dateObj = new Date(date * 1000);
            } else {
                dateObj = new Date(date);
            }
        } else if (typeof date === 'string') {
            dateObj = new Date(date);
        } else if (date instanceof Date) {
            dateObj = date;
        } else {
            return 'Invalid date';
        }
        
        // Validate the date is valid
        if (isNaN(dateObj.getTime())) {
            return 'Invalid date';
        }
        
        // Format as YYYY-MM-DD HH:MM:SS
        const year = dateObj.getFullYear();
        const month = String(dateObj.getMonth() + 1).padStart(2, '0');
        const day = String(dateObj.getDate()).padStart(2, '0');
        const hours = String(dateObj.getHours()).padStart(2, '0');
        const minutes = String(dateObj.getMinutes()).padStart(2, '0');
        const seconds = String(dateObj.getSeconds()).padStart(2, '0');
        
        return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
    } catch (error) {
        console.error('Error formatting datetime:', error, date);
        return 'Date error';
    }
}

/**
 * [2025-04-06 19:15] Show a notification message
 * @param {string} message - The message to show
 * @param {string} type - The type of notification (success, error, info)
 */
function showNotification(message, type = 'info') {
    // Create notification container if it doesn't exist
    let container = document.getElementById('notification-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'notification-container';
        document.body.appendChild(container);
    }
    
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    
    // Add to container
    container.appendChild(notification);
    
    // Remove after timeout
    setTimeout(() => {
        notification.classList.add('fade-out');
        setTimeout(() => {
            container.removeChild(notification);
        }, 300);
    }, 3000);
}

/**
 * [2025-05-24T13:50:00-04:00] Handle service request messages
 * This function displays service requests from workers in the monitor
 * @param {Object} message - The service request message
 * @param {string} source - Source of the message ('monitor' or 'client')
 */
function handleServiceRequest(message, source) {
    // [2025-05-25T10:30:00-04:00] Enhanced service request handling with better logging
    console.log('[2025-05-25T10:30:00-04:00] Received service request message:', message);
    
    // Log the service request
    const timestamp = new Date().toLocaleTimeString();
    const workerInfo = message.worker_id || 'Unknown worker';
    const jobInfo = message.job_id || 'Unknown job';
    const serviceInfo = message.service || 'Unknown service';
    const requestType = message.request_type || 'Unknown request';
    
    // Extract endpoint information if available
    let endpointInfo = '';
    if (message.content && message.content.endpoint) {
        endpointInfo = ` (${message.content.endpoint})`;
    }
    
    // Add log entry for the service request with more details
    addLogEntry(`Service request from ${workerInfo} for job ${jobInfo}: ${requestType}${endpointInfo} to ${serviceInfo}`, 'info');
    console.log(`[2025-05-25T10:30:00-04:00] Service request details - Worker: ${workerInfo}, Job: ${jobInfo}, Type: ${requestType}, Service: ${serviceInfo}`);
    
    // Create a service request item if the container exists
    if (elements.serviceRequestsList) {
        // Create a new service request item
        const requestItem = document.createElement('div');
        requestItem.className = 'service-request-item';
        requestItem.dataset.jobId = jobInfo;
        requestItem.dataset.timestamp = message.timestamp || Date.now();
        
        // Create header with basic info and endpoint if available
        const header = document.createElement('div');
        header.className = 'service-request-header';
        
        // Extract endpoint for display
        const endpoint = message.content && message.content.endpoint ? 
            `<span class="service-request-endpoint">${message.content.endpoint}</span>` : '';
        
        header.innerHTML = `
            <div class="service-request-info">
                <span class="service-request-timestamp">${timestamp}</span>
                <span class="service-request-worker">${workerInfo}</span>
                <span class="service-request-job">${jobInfo}</span>
                <span class="service-request-type">${requestType}</span>
                ${endpoint}
                <span class="service-request-service">${serviceInfo}</span>
            </div>
            <div class="service-request-actions">
                <button class="btn-view-request">View Request</button>
            </div>
        `;
        
        // Create content container (initially hidden)
        const content = document.createElement('div');
        content.className = 'service-request-content hidden';
        
        // Format the content as JSON with better formatting
        let formattedContent = 'No content available';
        try {
            if (message.content) {
                formattedContent = JSON.stringify(message.content, null, 2);
            }
        } catch (error) {
            console.error('[2025-05-25T10:30:00-04:00] Error formatting service request content:', error);
            formattedContent = `Error formatting content: ${error.message}`;
        }
        
        content.innerHTML = `<pre class="service-request-json">${formattedContent}</pre>`;
        
        // Add event listener to view button
        requestItem.appendChild(header);
        requestItem.appendChild(content);
        
        // Add click handler for the view button
        const viewButton = header.querySelector('.btn-view-request');
        viewButton.addEventListener('click', () => {
            content.classList.toggle('hidden');
            viewButton.textContent = content.classList.contains('hidden') ? 'View Request' : 'Hide Request';
        });
        
        // Add the request item to the list
        elements.serviceRequestsList.insertBefore(requestItem, elements.serviceRequestsList.firstChild);
        console.log('[2025-05-25T10:30:00-04:00] Added service request item to list');
        
        // Show the container and hide the no requests message
        if (elements.serviceRequestsContainer) {
            elements.serviceRequestsContainer.classList.remove('hidden');
        }
        if (elements.noServiceRequestsMessage) {
            elements.noServiceRequestsMessage.classList.add('hidden');
        }
        
        // Limit the number of displayed requests to prevent performance issues
        const maxRequests = 50;
        const requestItems = elements.serviceRequestsList.querySelectorAll('.service-request-item');
        if (requestItems.length > maxRequests) {
            for (let i = maxRequests; i < requestItems.length; i++) {
                elements.serviceRequestsList.removeChild(requestItems[i]);
            }
        }
    } else {
        console.error('[2025-05-25T10:30:00-04:00] Service requests list element not found');
    }
}

/**
 * [2025-05-25T09:30:00-04:00] Set up event delegation for job action buttons
 * This fixes the issue where job detail buttons need to be clicked twice
 */
function setupJobActionEventDelegation() {
    // Add event delegation for job queue table
    if (elements.jobsTableBody) {
        elements.jobsTableBody.addEventListener('click', function(event) {
            // Find the closest action button that was clicked
            const actionBtn = event.target.closest('.action-btn');
            if (actionBtn && actionBtn.getAttribute('data-action') === 'view-details') {
                // Get the job ID from the data attribute
                const jobId = actionBtn.getAttribute('data-job-id');
                if (jobId) {
                    // Call the showJobDetails function directly
                    showJobDetails(jobId);
                    // Prevent the default action and stop propagation
                    event.preventDefault();
                    event.stopPropagation();
                }
            }
        });
    }
    
    // Add event delegation for finished jobs table
    if (elements.finishedJobsTableBody) {
        elements.finishedJobsTableBody.addEventListener('click', function(event) {
            // Find the closest action button that was clicked
            const actionBtn = event.target.closest('.action-btn');
            if (actionBtn && actionBtn.getAttribute('data-action') === 'view-details') {
                // Get the job ID from the data attribute
                const jobId = actionBtn.getAttribute('data-job-id');
                if (jobId) {
                    // Call the showJobDetails function directly
                    showJobDetails(jobId);
                    // Prevent the default action and stop propagation
                    event.preventDefault();
                    event.stopPropagation();
                }
            }
        });
    }
}

// Initialize the application when the DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    init();
    setupJobActionEventDelegation();
    // Removed setupPeriodicRefresh() as we're using server push instead
});
