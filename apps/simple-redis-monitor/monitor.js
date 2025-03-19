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
    workerConnected: false,
    
    // Worker state
    workerSubscribed: false,
    
    // Redis entities
    workers: {},
    clients: {},
    jobs: {},
    
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
    workerSocket: null,   // For worker simulation
    
    // Pending requests tracking
    pendingRequests: {}
};

// DOM Elements
const elements = {
    // Connection controls
    websocketUrl: document.getElementById('websocket-url'),
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
    
    // Worker simulation controls
    subscribeBtn: document.getElementById('subscribe-btn'),
    unsubscribeBtn: document.getElementById('unsubscribe-btn'),
    subscriptionStatus: document.getElementById('subscription-status'),
    
    // Job submission
    jobType: document.getElementById('job-type'),
    jobPriority: document.getElementById('job-priority'),
    priorityButtons: document.querySelectorAll('.priority-btn'),
    jobPayload: document.getElementById('job-payload'),
    submitJobBtn: document.getElementById('submit-job-btn'),
    
    // Stats
    requestStatsBtn: document.getElementById('request-stats-btn'),
    workersCount: document.getElementById('workers-count'),
    clientsCount: document.getElementById('clients-count'),
    queuedJobsCount: document.getElementById('queued-jobs-count'),
    activeJobsCount: document.getElementById('active-jobs-count'),
    completedJobsCount: document.getElementById('completed-jobs-count'),
    
    // Tables
    workersTableBody: document.getElementById('workers-table-body'),
    jobsTableBody: document.getElementById('jobs-table-body'),
    noWorkersMessage: document.getElementById('no-workers-message'),
    noJobsMessage: document.getElementById('no-jobs-message'),
    workersTableContainer: document.getElementById('workers-table-container'),
    jobsTableContainer: document.getElementById('jobs-table-container'),
    
    // Logs
    logs: document.getElementById('logs')
};

/**
 * Initialize the application
 */
function init() {
    // Add event listeners
    elements.connectBtn.addEventListener('click', connect);
    elements.disconnectBtn.addEventListener('click', disconnect);
    elements.submitJobBtn.addEventListener('click', submitJob);
    
    // Add worker subscription event listeners
    if (elements.subscribeBtn) {
        elements.subscribeBtn.addEventListener('click', subscribeToJobNotifications);
    }
    
    if (elements.unsubscribeBtn) {
        elements.unsubscribeBtn.addEventListener('click', unsubscribeFromJobNotifications);
    }
    
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
 * Connect to Redis via WebSocket with monitor, client, and worker connections
 * Uses timestamp-based IDs for each connection type
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
    
    // Create IDs with the specified format using timestamps
    const clientId = `client-id-${timestamp}`;
    const monitorId = `monitor-id-${timestamp}`;
    const workerId = `worker-simulator-${timestamp}`;
    
    // Store IDs in state for reference
    state.clientId = clientId;
    state.monitorId = monitorId;
    state.workerId = workerId;
    
    // Show connection info display
    if (elements.connectionInfo) {
        elements.connectionInfo.style.display = 'flex';
    }
    
    // Update connection ID displays
    if (elements.monitorIdDisplay) {
        elements.monitorIdDisplay.textContent = monitorId;
    }
    
    if (elements.clientIdDisplay) {
        elements.clientIdDisplay.textContent = clientId;
    }
    

    
    // Log connection attempt with IDs
    addLogEntry(`Initializing connections with timestamp-based IDs (${new Date(timestamp).toLocaleTimeString()})`, 'info');
    
    // Connect monitor socket
    connectMonitorSocket(baseUrl, monitorId, authToken);
    
    // Connect client socket
    connectClientSocket(baseUrl, clientId, authToken);
    
    // Connect worker socket
    connectWorkerSocket(baseUrl, workerId, authToken);
}

/**
 * Connect the monitor socket for receiving system updates
 * @param {string} baseUrl - Base WebSocket URL
 * @param {string} monitorId - Monitor connection ID
 * @param {string} authToken - Authentication token
 */
function connectMonitorSocket(baseUrl, monitorId, authToken) {
    // Determine protocol (wss for https, ws for http)
    const protocol = baseUrl.startsWith('https://') ? 'wss' : 'ws';
    
    // Extract host and port from baseUrl
    let host = baseUrl;
    // Remove protocol prefix if present
    if (host.startsWith('http://')) host = host.substring(7);
    if (host.startsWith('https://')) host = host.substring(8);
    if (host.startsWith('ws://')) host = host.substring(5);
    if (host.startsWith('wss://')) host = host.substring(6);
    
    // Format the WebSocket URL with the monitor path - exactly like worker code
    const base_url = `${protocol}://${host}/ws/monitor/${monitorId}`;
    
    // Add authentication token if provided - exactly like worker code
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
            
            // Update UI if both connections are ready
            updateConnectionUI();
        });
        
        // Listen for messages
        state.monitorSocket.addEventListener('message', handleMonitorMessage);
        
        // Connection closed
        state.monitorSocket.addEventListener('close', (event) => {
            state.monitorConnected = false;
            addLogEntry('Monitor connection closed', 'warning');
            updateConnectionUI();
        });
        
        // Connection error
        state.monitorSocket.addEventListener('error', (event) => {
            addLogEntry('Monitor connection error', 'error');
            state.monitorConnected = false;
            updateConnectionUI();
        });
        
    } catch (error) {
        addLogEntry(`Error connecting monitor socket: ${error.message}`, 'error');
    }
}

/**
 * Connect the client socket for job submission
 * @param {string} baseUrl - Base WebSocket URL
 * @param {string} clientId - Client connection ID
 * @param {string} authToken - Authentication token
 */
function connectClientSocket(baseUrl, clientId, authToken) {
    // Determine protocol (wss for https, ws for http)
    const protocol = baseUrl.startsWith('https://') ? 'wss' : 'ws';
    
    // Extract host and port from baseUrl
    let host = baseUrl;
    // Remove protocol prefix if present
    if (host.startsWith('http://')) host = host.substring(7);
    if (host.startsWith('https://')) host = host.substring(8);
    if (host.startsWith('ws://')) host = host.substring(5);
    if (host.startsWith('wss://')) host = host.substring(6);
    
    // Format the WebSocket URL with the client path - exactly like worker code
    const base_url = `${protocol}://${host}/ws/client/${clientId}`;
    
    // Add authentication token if provided - exactly like worker code
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
            
            // Update UI if both connections are ready
            updateConnectionUI();
        });
        
        // Listen for messages
        state.clientSocket.addEventListener('message', handleClientMessage);
        
        // Connection closed
        state.clientSocket.addEventListener('close', (event) => {
            state.clientConnected = false;
            addLogEntry('Client connection closed', 'warning');
            updateConnectionUI();
        });
        
        // Connection error
        state.clientSocket.addEventListener('error', (event) => {
            addLogEntry('Client connection error', 'error');
            state.clientConnected = false;
            updateConnectionUI();
        });
        
    } catch (error) {
        addLogEntry(`Error connecting client socket: ${error.message}`, 'error');
    }
}

/**
 * Connect the worker socket for job notifications
 * @param {string} baseUrl - Base WebSocket URL
 * @param {string} workerId - Worker connection ID
 * @param {string} authToken - Authentication token
 */
function connectWorkerSocket(baseUrl, workerId, authToken) {
    // Determine protocol (wss for https, ws for http)
    const protocol = baseUrl.startsWith('https://') ? 'wss' : 'ws';
    
    // Extract host and port from baseUrl
    let host = baseUrl;
    // Remove protocol prefix if present
    if (host.startsWith('http://')) host = host.substring(7);
    if (host.startsWith('https://')) host = host.substring(8);
    if (host.startsWith('ws://')) host = host.substring(5);
    if (host.startsWith('wss://')) host = host.substring(6);
    
    // Format the WebSocket URL with the worker path - exactly like worker code
    const base_url = `${protocol}://${host}/ws/worker/${workerId}`;
    
    // Add authentication token if provided - exactly like worker code
    const workerUrl = authToken ? `${base_url}?token=${encodeURIComponent(authToken)}` : base_url;
    
    // Log the URL we're connecting to
    console.log('Worker URL:', workerUrl);
    
    addLogEntry(`Connecting worker socket as '${workerId}'...`, 'info');
    
    try {
        // Create worker WebSocket connection
        state.workerSocket = new WebSocket(workerUrl);
        
        // Connection opened
        state.workerSocket.addEventListener('open', (event) => {
            state.workerConnected = true;
            addLogEntry(`Worker connection established as '${workerId}'`, 'success');
            
            // Enable subscription buttons
            if (elements.subscribeBtn) {
                elements.subscribeBtn.disabled = false;
            }
            if (elements.unsubscribeBtn) {
                elements.unsubscribeBtn.disabled = true; // Initially disabled until subscribed
            }
            
            // Update UI
            updateConnectionUI();
        });
        
        // Listen for messages
        state.workerSocket.addEventListener('message', handleWorkerMessage);
        
        // Connection closed
        state.workerSocket.addEventListener('close', (event) => {
            state.workerConnected = false;
            state.workerSubscribed = false;
            addLogEntry('Worker connection closed', 'warning');
            
            // Disable subscription buttons
            if (elements.subscribeBtn) {
                elements.subscribeBtn.disabled = true;
            }
            if (elements.unsubscribeBtn) {
                elements.unsubscribeBtn.disabled = true;
            }
            
            // Update subscription status
            if (elements.subscriptionStatus) {
                elements.subscriptionStatus.textContent = 'Not subscribed';
            }
            
            // Update worker ID display
            if (elements.workerIdDisplay) {
                elements.workerIdDisplay.textContent = 'Not connected';
            }
            
            updateConnectionUI();
        });
        
        // Connection error
        state.workerSocket.addEventListener('error', (event) => {
            addLogEntry('Worker connection error', 'error');
            state.workerConnected = false;
            state.workerSubscribed = false;
            updateConnectionUI();
        });
        
    } catch (error) {
        addLogEntry(`Error connecting worker socket: ${error.message}`, 'error');
    }
}

/**
 * Update the connection UI based on connection states
 * This function handles the visual representation of connection states for
 * the monitor, client, and worker WebSocket connections
 */
function updateConnectionUI() {
    // Check connection states
    const allConnected = state.monitorConnected && state.clientConnected && state.workerConnected;
    const anyConnected = state.monitorConnected || state.clientConnected || state.workerConnected;
    
    // Update UI elements with null checks to prevent errors
    if (elements.connectBtn) {
        elements.connectBtn.disabled = anyConnected; // Disable connect if any connection is active
    }
    
    if (elements.disconnectBtn) {
        elements.disconnectBtn.disabled = !anyConnected; // Enable disconnect if any connection is active
    }
    
    if (elements.submitJobBtn) {
        elements.submitJobBtn.disabled = !state.clientConnected; // Only enable job submission if client is connected
    }
    
    if (elements.requestStatsBtn) {
        elements.requestStatsBtn.disabled = !state.monitorConnected; // Only enable stats requests if monitor is connected
    }
    
    // Create detailed connection status message
    let statusDetails = [];
    if (state.monitorConnected) {
        // Use the stored monitor ID from state if available
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
    
    if (state.clientConnected) {
        // Use the stored client ID from state if available
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
    
    if (state.workerConnected) {
        // Use the stored worker ID from state if available
        const workerId = state.workerId || 'unknown';
        const subscriptionStatus = state.workerSubscribed ? 'Subscribed' : 'Not subscribed';
        statusDetails.push(`Worker: Connected (${workerId}) - ${subscriptionStatus}`);
        
        // Update worker ID display if available
        if (elements.workerIdDisplay) {
            elements.workerIdDisplay.textContent = workerId;
        }
    } else {
        statusDetails.push('Worker: Disconnected');
        
        // Reset worker ID display if available
        if (elements.workerIdDisplay) {
            elements.workerIdDisplay.textContent = 'Not connected';
        }
    }
    
    // Update connection status indicator and text with null checks
    if (elements.statusIndicator) {
        if (allConnected) {
            // All connections active
            elements.statusIndicator.classList.remove('status-disconnected', 'status-partial');
            elements.statusIndicator.classList.add('status-connected');
        } else if (anyConnected) {
            // At least one connection active - partial connection state
            elements.statusIndicator.classList.remove('status-disconnected', 'status-connected');
            elements.statusIndicator.classList.add('status-partial');
        } else {
            // No connections active
            elements.statusIndicator.classList.remove('status-connected', 'status-partial');
            elements.statusIndicator.classList.add('status-disconnected');
        }
    }
    
    if (elements.connectionStatusText) {
        if (allConnected) {
            // All connections active
            elements.connectionStatusText.textContent = 'Fully Connected';
            elements.connectionStatusText.title = statusDetails.join('\n');
        } else if (anyConnected) {
            // At least one connection active - partial connection state
            // Show which connection is active in the UI
            if (state.monitorConnected && !state.clientConnected) {
                elements.connectionStatusText.textContent = 'Monitor Connected (client offline)';
                addLogEntry('Monitor connection active, but client connection is offline', 'warning');
            } else if (!state.monitorConnected && state.clientConnected) {
                elements.connectionStatusText.textContent = 'Client Connected (monitor offline)';
                addLogEntry('Client connection active, but monitor connection is offline', 'warning');
            } else {
                elements.connectionStatusText.textContent = 'Partially Connected';
            }
            
            // Add tooltip with detailed connection status
            elements.connectionStatusText.title = statusDetails.join('\n');
        } else {
            // No connections active
            elements.connectionStatusText.textContent = 'Disconnected';
            elements.connectionStatusText.title = 'Both monitor and client connections are offline';
            
            addLogEntry('All connections are offline', 'warning');
        }
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
    
    // Close worker socket if it exists
    if (state.workerSocket) {
        state.workerSocket.close();
    }
    
    handleDisconnect();
}

/**
 * Handle disconnection (either manual or due to error)
 * Resets connection states and UI elements
 */
function handleDisconnect() {
    // Reset connection states
    state.monitorConnected = false;
    state.clientConnected = false;
    state.workerConnected = false;
    state.workerSubscribed = false;
    
    // Clear socket references
    state.monitorSocket = null;
    state.clientSocket = null;
    state.workerSocket = null;
    
    // Reset connection info display
    if (elements.connectionInfo) {
        // Hide the connection info display
        elements.connectionInfo.style.display = 'none';
    }
    
    // Reset connection ID displays
    if (elements.monitorIdDisplay) {
        elements.monitorIdDisplay.textContent = 'Not connected';
    }
    
    if (elements.clientIdDisplay) {
        elements.clientIdDisplay.textContent = 'Not connected';
    }
    
    if (elements.workerIdDisplay) {
        elements.workerIdDisplay.textContent = 'Not connected';
    }
    
    // Reset subscription status
    if (elements.subscriptionStatus) {
        elements.subscriptionStatus.textContent = 'Not subscribed';
    }
    
    // Disable subscription buttons
    if (elements.subscribeBtn) {
        elements.subscribeBtn.disabled = true;
    }
    if (elements.unsubscribeBtn) {
        elements.unsubscribeBtn.disabled = true;
    }
    
    // Clear connection IDs from state
    state.monitorId = null;
    state.clientId = null;
    state.workerId = null;
    
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
        completedJobs: 0,
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
    processMessage(event.data, 'client');
}

/**
 * Handle incoming messages from the worker socket
 * @param {MessageEvent} event - WebSocket message event
 */
function handleWorkerMessage(event) {
    processMessage(event.data, 'worker');
}

/**
 * Subscribe worker to job notifications
 * Sends a subscription request to the server
 */
function subscribeToJobNotifications() {
    // Check if worker is connected
    if (!state.workerConnected || !state.workerSocket) {
        addLogEntry('Cannot subscribe: Worker not connected', 'error');
        return;
    }
    
    // Check if already subscribed
    if (state.workerSubscribed) {
        addLogEntry('Worker already subscribed to job notifications', 'warning');
        return;
    }
    
    try {
        // Create subscription message using the server's expected format
        const subscriptionMessage = {
            type: 'subscribe_job_notifications',
            worker_id: state.workerId,
            enabled: true,
            timestamp: Date.now() / 1000 // Convert to seconds to match Python's time.time()
        };
        
        // Send the message
        state.workerSocket.send(JSON.stringify(subscriptionMessage));
        
        addLogEntry('Sending job notifications subscription request...', 'info');
        
    } catch (error) {
        addLogEntry(`Error subscribing to job notifications: ${error.message}`, 'error');
    }
}

/**
 * Unsubscribe worker from job notifications
 * Sends an unsubscription request to the server
 */
function unsubscribeFromJobNotifications() {
    // Check if worker is connected
    if (!state.workerConnected || !state.workerSocket) {
        addLogEntry('Cannot unsubscribe: Worker not connected', 'error');
        return;
    }
    
    // Check if already unsubscribed
    if (!state.workerSubscribed) {
        addLogEntry('Worker not currently subscribed to job notifications', 'warning');
        return;
    }
    
    try {
        // Create unsubscription message using the server's expected format
        const unsubscriptionMessage = {
            type: 'subscribe_job_notifications',  // Same type as subscribe, but with enabled=false
            worker_id: state.workerId,
            enabled: false,
            timestamp: Date.now() / 1000 // Convert to seconds to match Python's time.time()
        };
        
        // Send the message
        state.workerSocket.send(JSON.stringify(unsubscriptionMessage));
        
        addLogEntry('Sending job notifications unsubscription request...', 'info');
        
        // Update UI immediately (server will confirm with a response)
        state.workerSubscribed = false;
        
        // Update subscription status
        if (elements.subscriptionStatus) {
            elements.subscriptionStatus.textContent = 'Unsubscribing...';
        }
        
        // Update button states
        if (elements.subscribeBtn) {
            elements.subscribeBtn.disabled = true;
        }
        if (elements.unsubscribeBtn) {
            elements.unsubscribeBtn.disabled = true;
        }
        
    } catch (error) {
        addLogEntry(`Error unsubscribing from job notifications: ${error.message}`, 'error');
    }
}

/**
 * Process WebSocket messages from any connection
 * @param {string} data - Raw message data
 * @param {string} source - Source of the message ('monitor', 'client', or 'worker')
 */
function processMessage(data, source) {
    try {
        // Parse the raw JSON message
        const rawMessage = JSON.parse(data);
        
        if (!rawMessage.type) {
            addLogEntry(`Received ${source} message with no type`, 'error');
            return;
        }
        
        // Log received message with source
        addLogEntry(`Received ${source} message: ${rawMessage.type}`, 'info');
        
        try {
            // Parse the message using our Messages class
            const parsedMessage = Messages.parseMessage(rawMessage);
            
            // Handle different message types
            switch (rawMessage.type) {
                case Messages.TYPE.RESPONSE_STATS:
                    handleStatsResponse(parsedMessage, rawMessage, source);
                    break;
                case Messages.TYPE.JOB_ACCEPTED:
                    handleJobAccepted(parsedMessage, source);
                    break;
                case Messages.TYPE.UPDATE_JOB_PROGRESS:
                    handleJobProgress(parsedMessage, source);
                    break;
                case Messages.TYPE.COMPLETE_JOB:
                    handleJobCompleted(parsedMessage, source);
                    break;
                case Messages.TYPE.FAIL_JOB:
                    handleJobFailed(parsedMessage, rawMessage, source);
                    break;
                case Messages.TYPE.WORKER_REGISTERED:
                    handleWorkerRegistered(parsedMessage, rawMessage, source);
                    break;
                case Messages.TYPE.WORKER_STATUS:
                    handleWorkerStatus(parsedMessage, source);
                    break;
                case Messages.TYPE.ERROR:
                    handleErrorMessage(parsedMessage, source);
                    break;
                case Messages.TYPE.CONNECTION_ESTABLISHED:
                    addLogEntry(`${source.charAt(0).toUpperCase() + source.slice(1)} connection established: ${rawMessage.message}`, 'success');
                    break;
                case Messages.TYPE.STATS_BROADCAST:
                    handleStatsBroadcast(parsedMessage, rawMessage, source);
                    break;
                case Messages.TYPE.ACK:
                    handleAckMessage(parsedMessage, rawMessage, source);
                    break;
                case Messages.TYPE.REQUEST_STATS:
                    // This is a request_stats message we sent and received back
                    // Just log it for debugging purposes
                    console.log(`Received request_stats echo from ${source}:`, rawMessage);
                    break;
                case 'subscribe_job_notifications':
                    // Worker is trying to subscribe to job notifications
                    if (source === 'worker') {
                        const action = rawMessage.enabled ? 'subscribe to' : 'unsubscribe from';
                        addLogEntry(`Worker ${rawMessage.worker_id} requesting to ${action} job notifications`, 'info');
                    }
                    break;
                case 'job_notifications_subscribed':
                    // Worker successfully subscribed to job notifications
                    if (source === 'worker') {
                        state.workerSubscribed = true;
                        addLogEntry(`Worker ${rawMessage.worker_id} subscribed to job notifications`, 'success');
                        
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
                        addLogEntry(`Worker ${rawMessage.worker_id} unsubscribed from job notifications`, 'info');
                        
                        // Update subscription status
                        if (elements.subscriptionStatus) {
                            elements.subscriptionStatus.textContent = 'Not subscribed';
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
                case 'job_notification':
                    // Worker received a job notification
                    if (source === 'worker') {
                        addLogEntry(`Worker received job notification for job: ${rawMessage.job_id}`, 'info');
                    }
                    break;
                default:
                    // Log unknown message types with more detail
                    addLogEntry(`Received unhandled ${source} message type: ${rawMessage.type}`, 'warning');
                    // Store unhandled message types for debugging
                    if (!state.unhandledMessageTypes) {
                        state.unhandledMessageTypes = {};
                    }
                    if (!state.unhandledMessageTypes[rawMessage.type]) {
                        state.unhandledMessageTypes[rawMessage.type] = [];
                    }
                    // Store up to 5 examples of each unhandled type
                    if (state.unhandledMessageTypes[rawMessage.type].length < 5) {
                        state.unhandledMessageTypes[rawMessage.type].push({
                            ...rawMessage,
                            _source: source,
                            _receivedAt: new Date().toISOString()
                        });
                    }
            }
        } catch (parseError) {
            // If parsing fails, fall back to using the raw message
            addLogEntry(`Error parsing ${source} message structure: ${parseError.message}`, 'warning');
            console.warn(`${source} message parsing error:`, parseError, 'Raw message:', rawMessage);
            
            // Handle the message using the raw format as fallback
            handleRawMessage(rawMessage, source);
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
        
        // Extract stats from the response
        const queues = statsData.queues || {};
        const jobs = statsData.jobs || {};
        const workers = statsData.workers || {};
        
        // Update state with the new stats
        state.stats.totalWorkers = workers.total || 0;
        state.stats.totalClients = (statsData.connections && statsData.connections.clients) || 0;
        
        // Update job counts
        state.stats.activeJobs = (jobs.status && jobs.status.active) || 0;
        state.stats.pendingJobs = (jobs.status && jobs.status.pending) || 0;
        state.stats.queuedJobs = state.stats.pendingJobs; // Map pending jobs to queued jobs for UI display
        state.stats.completedJobs = (jobs.status && jobs.status.completed) || 0;
        state.stats.failedJobs = (jobs.status && jobs.status.failed) || 0;
        
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
            statsData.jobs.active_jobs.forEach(jobData => {
                // Make sure we have a job ID
                const jobId = jobData.id;
                if (!jobId) {
                    console.warn('[WARNING] Job data missing ID:', jobData);
                    return; // Skip this job
                }
                
                // Update or add job to state
                state.jobs[jobId] = {
                    ...state.jobs[jobId],
                    ...jobData,
                    id: jobId,
                    job_type: jobData.job_type || jobData.type || '',
                    priority: parseInt(jobData.priority || 0),
                    position: jobData.position || parseInt(jobData.priority || 0)  // Use priority as position if position is not available
                };
            });
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
    
    // Update workers in state
    state.workers = {};
    Object.entries(workers).forEach(([workerId, workerData]) => {
        // Create a worker object with all available information
        const is_accepting_jobs = system.workers.active_workers.includes(workerId);
        state.workers[workerId] = {
            id: workerId,
            status: workerData.status || 'unknown',
            connectionStatus: workerData.connection_status || workerData.status || 'unknown',
            connectedAt: Date.now(), // We don't have the exact time, so use current time
            jobsProcessed: workerData.jobs_processed || 0,
            is_accepting_jobs: system.workers.active_workers.find(w => w.id === workerId) !== undefined,
            // Add any additional worker data that might be useful
            lastSeen: new Date().toLocaleTimeString()
        };
    });
    
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
    
    // Update stats
    state.stats.totalWorkers = Object.keys(workers).length;
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
 * Handle job accepted message
 * @param {Object} message - Parsed job accepted message
 * @param {string} source - Source of the message ('monitor' or 'client')
 */
function handleJobAccepted(message, source = 'unknown') {
    const jobId = message.jobId;
    const status = message.status;
    const position = message.position;
    
    // Add job to state
    state.jobs[jobId] = {
        id: jobId,
        status: status || 'pending',
        position: position,
        progress: 0,
        createdAt: new Date(),
        updatedAt: new Date()
    };
    
    addLogEntry(`Job accepted: ${jobId}`, 'success');
}

/**
 * Handle job progress update message
 * @param {Object} message - Parsed job progress message
 * @param {string} source - Source of the message ('monitor' or 'client')
 */
function handleJobProgress(message, source = 'unknown') {
    const jobId = message.jobId;
    const progress = message.progress;
    const status = message.status;
    const workerId = message.workerId;
    
    // Update job in state
    if (state.jobs[jobId]) {
        state.jobs[jobId].progress = progress;
        state.jobs[jobId].status = status || 'processing';
        state.jobs[jobId].workerId = workerId;
        state.jobs[jobId].updatedAt = new Date();
    } else {
        // If job doesn't exist in state, add it
        state.jobs[jobId] = {
            id: jobId,
            status: status || 'processing',
            progress: progress,
            workerId: workerId,
            createdAt: new Date(),
            updatedAt: new Date()
        };
    }
    
    addLogEntry(`Job ${jobId} progress: ${progress}%`, 'info');
}

/**
 * Handle job completed message
 * @param {Object} message - Parsed job completed message
 * @param {string} source - Source of the message ('monitor' or 'client')
 */
function handleJobCompleted(message, source = 'unknown') {
    const jobId = message.jobId;
    const result = message.result;
    
    // Update job in state
    if (state.jobs[jobId]) {
        state.jobs[jobId].status = 'completed';
        state.jobs[jobId].progress = 100;
        state.jobs[jobId].result = result;
        state.jobs[jobId].updatedAt = new Date();
        
        // Remove job from active jobs after a delay
        setTimeout(() => {
            delete state.jobs[jobId];
            updateUI();
        }, 5000);
    }
    
    // Update stats
    state.stats.completedJobs++;
    state.stats.activeJobs = Math.max(0, state.stats.activeJobs - 1);
    
    addLogEntry(`Job ${jobId} completed`, 'success');
}

/**
 * Handle job failed message
 * @param {Object} parsedMessage - Parsed job failed message
 * @param {Object} rawMessage - Raw message object (fallback)=
 * @param {string} source - Source of the message ('monitor' or 'client')
 */
function handleJobFailed(parsedMessage, rawMessage, source = 'unknown') {
    // Use parsed message if available, otherwise fallback to raw message
    const message = parsedMessage || rawMessage;
    const jobId = parsedMessage ? parsedMessage.jobId : rawMessage.job_id;
    const errorMsg = parsedMessage ? parsedMessage.error : rawMessage.error;
    
    // Update job in state
    if (state.jobs[jobId]) {
        state.jobs[jobId].status = 'failed';
        state.jobs[jobId].error = errorMsg;
        state.jobs[jobId].updatedAt = new Date();
        
        // Remove job from active jobs after a delay
        setTimeout(() => {
            delete state.jobs[jobId];
            updateUI();
        }, 5000);
    }
    
    // Update stats
    state.stats.failedJobs++;
    state.stats.activeJobs = Math.max(0, state.stats.activeJobs - 1);
    
    addLogEntry(`Job ${jobId} failed: ${errorMsg}`, 'error');
}

/**
 * Handle worker registered message
 * @param {Object} parsedMessage - Parsed worker registered message
 * @param {Object} rawMessage - Raw message object (fallback)
 * @param {string} source - Source of the message ('monitor' or 'client')
 */
function handleWorkerRegistered(parsedMessage, rawMessage, source = 'unknown') {
    // Use parsed message if available, otherwise fallback to raw message
    const message = parsedMessage || rawMessage;
    const workerId = parsedMessage ? parsedMessage.workerId : rawMessage.worker_id;
    const status = parsedMessage ? parsedMessage.status : rawMessage.status;
    
    // Add worker to state
    state.workers[workerId] = {
        id: workerId,
        status: status || 'active',
        connectedAt: new Date(),
        jobsProcessed: 0
    };
    
    // Update stats
    state.stats.totalWorkers++;
    
    addLogEntry(`Worker registered: ${workerId}`, 'info');
}

/**
 * Handle worker status update message
 * @param {Object} message - Parsed worker status message
 * @param {string} source - Source of the message ('monitor' or 'client')
 */
function handleWorkerStatus(message, source = 'unknown') {
    const workerId = message.workerId;
    const status = message.status;
    
    // Update worker in state
    if (state.workers[workerId]) {
        state.workers[workerId].status = status;
        state.workers[workerId].updatedAt = new Date();
    } else {
        // If worker doesn't exist in state, add it
        state.workers[workerId] = {
            id: workerId,
            status: status,
            connectedAt: new Date(),
            updatedAt: new Date(),
            jobsProcessed: 0
        };
        
        // Update stats
        state.stats.totalWorkers++;
    }
    
    addLogEntry(`Worker ${workerId} status: ${status}`, 'info');
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
 * Submit a job to Redis using the client connection
 */
function submitJob() {
    // Debug logging
    
    if (!state.clientConnected) {
        addLogEntry('Cannot submit job: Client connection not active', 'error');
        return;
    }
    
    try {
        // Get job details from form
        const jobType = elements.jobType.value;
        
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
        
        // Add a message ID for tracking
        message.message_id = `job-submit-${Date.now()}`;
        
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
        if (activeButton) {
            // Flash the button to indicate submission
            activeButton.classList.add('btn-flash');
            setTimeout(() => {
                activeButton.classList.remove('btn-flash');
            }, 500);
        }
        
        addLogEntry(`Submitted job of type '${jobType}' with priority ${priority}`, 'success');
    } catch (error) {
        console.error('Job submission error:', error);
        addLogEntry(`Error submitting job: ${error.message}`, 'error');
    }
}

/**
 * Request system statistics
 * Sends a request_stats message to the server to get current system statistics
 */
function requestStats() {
    if (!state.monitorConnected) {
        addLogEntry('Cannot request stats: Monitor connection not active', 'warning');
        return;
    }
    
    try {
        // Create request stats message using Messages class
        const message = Messages.createRequestStatsMessage();
        
        // Add a message ID for tracking
        message.message_id = `stats-request-${Date.now()}`;
        
        // Log the request
        addLogEntry('Requesting system statistics...', 'info');
        
        // Send message through the monitor connection
        state.monitorSocket.send(JSON.stringify(message));
        
        // Store the request in state for tracking
        if (!state.pendingRequests) {
            state.pendingRequests = {};
        }
        state.pendingRequests[message.message_id] = {
            type: message.type,
            timestamp: message.timestamp,
            status: 'pending'
        };
    } catch (error) {
        addLogEntry(`Error requesting stats: ${error.message}`, 'error');
        console.error('Error details:', error);
    }
}

/**
 * Update the UI with current state
 */
function updateUI() {
    // Update stats
    elements.workersCount.textContent = state.stats.totalWorkers;
    elements.clientsCount.textContent = state.stats.totalClients;
    elements.queuedJobsCount.textContent = state.stats.queuedJobs;
    elements.activeJobsCount.textContent = state.stats.activeJobs;
    elements.completedJobsCount.textContent = state.stats.completedJobs;
    
    // Update workers table
    const workers = Object.values(state.workers);
    elements.workersTableBody.innerHTML = '';
    
    if (workers.length > 0) {
        elements.workersTableContainer.classList.remove('hidden');
        elements.noWorkersMessage.classList.add('hidden');
        
        workers.forEach(worker => {
            const row = document.createElement('tr');
            // Format status class
            let statusClass = 'status-idle';
            if (worker.status === 'active' || worker.status === 'busy') statusClass = 'status-active';
            if (worker.status === 'error' || worker.status === 'out_of_service') statusClass = 'status-error';
            
            // Add accepting jobs indicator

            const acceptingJobsClass = worker.is_accepting_jobs ? 'status-active' : 'status-error';
            const acceptingJobsText = worker.is_accepting_jobs ? 'Yes' : 'No';
            
            row.innerHTML = `
                <td>${worker.id}</td>
                <td><span class="status ${statusClass}">${worker.status}</span></td>
                <td><span class="status ${acceptingJobsClass}">${acceptingJobsText}</span></td>
                <td>${formatRelativeTime(worker.connectedAt)}</td>
                <td>${worker.jobsProcessed || 0}</td>
            `;
            
            elements.workersTableBody.appendChild(row);
        });
    } else {
        elements.workersTableContainer.classList.add('hidden');
        elements.noWorkersMessage.classList.remove('hidden');
    }
    
    // Update jobs table
    
    const activeJobs = Object.values(state.jobs).filter(job => job.status === 'pending' || job.status === 'processing');

    elements.jobsTableBody.innerHTML = '';
    
    if (activeJobs.length > 0) {
        elements.jobsTableContainer.classList.remove('hidden');
        elements.noJobsMessage.classList.add('hidden');
        
        // Sort jobs by created_at timestamp (oldest first)
        activeJobs.sort((a, b) => {
            // Get raw created_at values
            const aCreatedAt = a.created_at || 0;
            const bCreatedAt = b.created_at || 0;
            
            // Sort by created_at (oldest first)
            return aCreatedAt - bCreatedAt;
        });
        
        activeJobs.forEach(job => {
            // Log individual job data for debugging
            
            const row = document.createElement('tr');
            
            // Format status class
            let statusClass = 'status-idle';
            if (job.status === 'pending') statusClass = 'status-queued';
            if (job.status === 'processing') statusClass = 'status-active';
            if (job.status === 'completed') statusClass = 'status-active';
            if (job.status === 'failed') statusClass = 'status-error';
            
            // Create progress bar
            const progressBar = `
                <div class="progress-container">
                    <div class="progress-bar" style="width: ${job.progress || 0}%">
                        ${job.progress || 0}%
                    </div>
                </div>
            `;
            
            // Use job_type, fallback to type, never show "unknown"
            // Force priority to be a number and log it

            const displayPriority = parseInt(job.priority || 0);

            
            // Get the raw created_at timestamp
            const rawCreatedAt = job.created_at || 'N/A';

            
            // Get the JavaScript Date object string representation
            const createdAtStr = job.createdAt ? job.createdAt.toString() : 'N/A';

            
            row.innerHTML = `
                <td>${job.id}</td>
                <td>${job.job_type || job.type || ''}</td>
                <td><span class="status ${statusClass}">${job.status}</span></td>
                <td>${displayPriority}</td>
                <td>${job.position !== undefined ? job.position : 'N/A'}</td>
                <td>${progressBar}</td>
                <td>${rawCreatedAt}</td>
                <td>${createdAtStr}</td>
                <td>${formatRelativeTime(job.updatedAt)}</td>
            `;
            
            elements.jobsTableBody.appendChild(row);
        });
    } else {
        elements.jobsTableContainer.classList.add('hidden');
        elements.noJobsMessage.classList.remove('hidden');
    }
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

// Periodic stats refresh removed as we're using server push instead

// Initialize the application when the DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    init();
    // Removed setupPeriodicRefresh() as we're using server push instead
});
