'use client';

import { useEffect, useState } from 'react';
import { useAppStore } from '@/lib/store';
import { getWebSocketManager } from '@/lib/websocket';
import { formatRelativeTime } from '@/lib/utils';
import { Message, MessageType, getMessageData, MonitorMessageType } from '@/lib/types/messages';

/**
 * System Monitor Dashboard
 * 
 * This page displays detailed information about the Redis system, including
 * workers, jobs, and system status.
 */
export default function DashboardPage() {
  const { 
    workers, 
    jobs, 
    stats, 
    setConnectionState,
    addWorker,
    updateWorker,
    removeWorker,
    addJob,
    updateJob,
    removeJob,
    updateStats
  } = useAppStore();
  const [isClient, setIsClient] = useState(false);
  const [lastMessage, setLastMessage] = useState<any>(null);
  // Initialize WebSocket connection on client-side only
  useEffect(() => {
    setIsClient(true);
    console.log('🔍 Dashboard: Initializing WebSocket connections');
    
    // Get WebSocket managers with proper configuration
    const clientManager = getWebSocketManager('client');
    const monitorManager = getWebSocketManager('monitor', {
      endpoint: '/ws/monitor' // This is critical - default is '/ws/client'
    });
    
    // Initial connection status check and connect if needed
    const checkConnectionStatus = () => {
      const clientConnected = clientManager.isConnected();
      const monitorConnected = monitorManager.isConnected();
      
      // Only log connection status once at startup and when there's a change
      console.log('🔍 Connection Status - Client:', clientConnected, 'Monitor:', monitorConnected);
      
      // Update the UI state based on the current connection status
      setConnectionState('client', { 
        connected: clientConnected,
        status: clientConnected ? 'connected' : 'disconnected'
      });
      
      setConnectionState('monitor', { 
        connected: monitorConnected,
        status: monitorConnected ? 'connected' : 'disconnected'
      });
      
      // Ensure connections are established
      if (!clientConnected) {
        console.log('🔍 Dashboard: Connecting to client WebSocket...');
        clientManager.connect();
      }
      
      if (!monitorConnected) {
        console.log('🔍 Dashboard: Connecting to monitor WebSocket...');
        monitorManager.connect();
      }
    };
    
    // Do initial check
    checkConnectionStatus();
    
    // Set up periodic check (every 5 seconds)
    const intervalId = setInterval(checkConnectionStatus, 5000);
    console.log('🔍 Dashboard: Connection check interval set up');
    
    // Set up message handlers
    clientManager.on(MessageType.WORKER_STATUS, (message: Message) => {
      const data = getMessageData(message);
      console.log('🔍 Worker Status:', data);
      
      if (data.workers) {
        // Update workers in store
        Object.entries(data.workers).forEach(([id, workerData]: [string, any]) => {
          addWorker({
            id,
            status: workerData.status,
            lastSeen: workerData.last_seen,
            capabilities: workerData.capabilities
          });
        });
        
        // Update stats
        if (data.stats) {
          updateStats({
            workers: {
              total: data.stats.workers_total || 0,
              active: data.stats.workers_active || 0,
              idle: data.stats.workers_idle || 0,
              busy: data.stats.workers_busy || 0,
            }
          });
        }
      }
    });
    
    clientManager.on(MessageType.JOB_STATUS, (message: Message) => {
      const data = getMessageData(message);
      
      if (data.jobs) {
        // Update jobs in store
        Object.entries(data.jobs).forEach(([id, jobData]: [string, any]) => {
          addJob({
            id,
            type: jobData.type,
            status: jobData.status,
            priority: jobData.priority,
            progress: jobData.progress,
            worker_id: jobData.worker_id,
            submitted_at: jobData.submitted_at,
            started_at: jobData.started_at,
            completed_at: jobData.completed_at,
            result: jobData.result,
            message: jobData.message
          });
        });
        
        // Update stats
        if (data.stats) {
          updateStats({
            jobs: {
              total: data.stats.jobs_total || 0,
              pending: data.stats.jobs_pending || 0,
              processing: data.stats.jobs_processing || 0,
              completed: data.stats.jobs_completed || 0,
              failed: data.stats.jobs_failed || 0,
            }
          });
        }
      }
    });
    
    // Use STATS_RESPONSE for client statistics
    clientManager.on(MessageType.STATS_RESPONSE, (message: Message) => {
      const data = getMessageData(message);
      
      if (data.stats) {
        updateStats({
          clients: {
            total: data.stats.clients_total || 0,
          }
        });
      }
    });
    
    // Handle STATS_BROADCAST messages from the system monitor
    // NOTE: We're using monitorManager here, not clientManager
    console.log('🔍 Dashboard: Setting up STATS_BROADCAST handler on MONITOR connection for', MessageType.STATS_BROADCAST);
    
    // Define the handler function separately so we can remove it later
    const handleStatsBroadcast = (message: Message) => {
      console.log('🔍 Dashboard: MONITOR STATS_BROADCAST handler called with message type:', message.type);
      
      // Store the raw message for display
      console.log('🔍 Dashboard: Raw STATS_BROADCAST message:', message);
      
      const data = getMessageData(message);
      console.log('🔍 Dashboard: Parsed MONITOR STATS_BROADCAST data:', JSON.stringify(data, null, 2));
      
      // Save the message data to state for display
      setLastMessage(data);
      
      // Update workers information
      if (data.workers && typeof data.workers === 'object') {
        console.log('🔍 Dashboard: Found workers data in MONITOR message, worker count:', Object.keys(data.workers).length);
        
        // Clear existing workers first to avoid stale data
        const existingWorkerCount = Object.keys(workers).length;
        console.log('🔍 Dashboard: Clearing existing workers, count:', existingWorkerCount);
        
        // Only clear if we have new workers to add
        if (Object.keys(data.workers).length > 0) {
          Object.keys(workers).forEach(workerId => {
            removeWorker(workerId);
          });
          
          // Add all workers from the broadcast
          console.log('🔍 Dashboard: Adding workers from MONITOR broadcast');
          Object.entries(data.workers).forEach(([id, workerData]: [string, any]) => {
            console.log('🔍 Dashboard: Adding worker from MONITOR:', id, workerData);
            addWorker({
              id,
              status: workerData.status || workerData.connection_status || 'unknown',
              lastSeen: workerData.last_seen || Date.now()/1000,
              capabilities: workerData.capabilities || []
            });
          });
        }
      } else {
        console.log('🔍 Dashboard: No valid workers data found in MONITOR message');
      }
      
      // Update system stats
      if (data.system) {
        console.log('🔍 Dashboard: Found system data in MONITOR message:', data.system);
        const systemData = data.system;
        
        // Update worker stats
        // First check if we have worker data directly in the message
        if (data.workers && typeof data.workers === 'object') {
          console.log('🔍 Dashboard: Found workers directly in message:', data.workers);
          const activeWorkers = Object.values(data.workers || {}).filter((w: any) => 
            w.status === 'active' || w.connection_status === 'active'
          ).length;
          const idleWorkers = Object.values(data.workers || {}).filter((w: any) => 
            w.status === 'idle' || w.connection_status === 'idle'
          ).length;
          const busyWorkers = Object.values(data.workers || {}).filter((w: any) => 
            w.status === 'busy' || w.connection_status === 'busy'
          ).length;
          
          // Use the system data for total count, or count from the workers object
          const totalWorkers = systemData.workers?.total || Object.keys(data.workers).length;
          
          console.log('🔍 Dashboard: MONITOR Worker counts - total:', totalWorkers, 
            'active:', activeWorkers, 'idle:', idleWorkers, 'busy:', busyWorkers);
          
          updateStats({
            workers: {
              total: totalWorkers,
              active: activeWorkers,
              idle: idleWorkers,
              busy: busyWorkers,
            }
          });
        } else if (systemData.workers) {
          console.log('🔍 Dashboard: No direct workers data, using system.workers:', systemData.workers);
          updateStats({
            workers: {
              total: systemData.workers.total || 0,
              active: 0, // We don't have detailed status in this case
              idle: 0,
              busy: 0,
            }
          });
        } else {
          console.log('🔍 Dashboard: No worker stats found in MONITOR message');
        }
        
        // Update job stats
        if (systemData.jobs) {
          console.log('🔍 Dashboard: Updating job stats from MONITOR with:', systemData.jobs);
          const jobStats = {
            total: systemData.jobs.total || 0,
            pending: (systemData.jobs.status?.pending || 0),
            processing: (systemData.jobs.status?.processing || 0),
            completed: (systemData.jobs.status?.completed || 0),
            failed: (systemData.jobs.status?.failed || 0),
          };
          console.log('🔍 Dashboard: MONITOR Job counts:', jobStats);
          updateStats({ jobs: jobStats });
        } else if (data.jobs) {
          // Try to get job data directly from the message
          console.log('🔍 Dashboard: Using job data directly from message:', data.jobs);
          const jobStats = {
            total: data.jobs.total || 0,
            pending: (data.jobs.status?.pending || 0),
            processing: (data.jobs.status?.processing || 0),
            completed: (data.jobs.status?.completed || 0),
            failed: (data.jobs.status?.failed || 0),
          };
          console.log('🔍 Dashboard: Direct job counts:', jobStats);
          updateStats({ jobs: jobStats });
        } else {
          console.log('🔍 Dashboard: No job stats found in MONITOR system data or message');
        }
        
        // Update client stats
        if (data.connections && data.connections.clients) {
          const clientCount = data.connections.clients.length || 0;
          console.log('🔍 Dashboard: Updating client stats from MONITOR connections, count:', clientCount);
          updateStats({
            clients: {
              total: clientCount,
            }
          });
        } else if (systemData.connections && systemData.connections.clients) {
          // Try to get client data from system data
          const clientCount = systemData.connections.clients.length || 0;
          console.log('🔍 Dashboard: Updating client stats from system data, count:', clientCount);
          updateStats({
            clients: {
              total: clientCount,
            }
          });
        } else {
          console.log('🔍 Dashboard: No client connection data found in MONITOR message');
          // Default to 0 clients if no data found
          updateStats({
            clients: {
              total: 0,
            }
          });
        }
      }
    }
    
    return () => {
      clearInterval(intervalId);
    };
  }, [
    setConnectionState, 
    addWorker, 
    updateWorker, 
    removeWorker, 
    addJob, 
    updateJob, 
    removeJob, 
    updateStats
  ]);
  
  // Get sorted workers and jobs
  const sortedWorkers = Object.values(workers).sort((a, b) => 
    a.status === 'active' && b.status !== 'active' ? -1 : 
    a.status !== 'active' && b.status === 'active' ? 1 : 
    a.lastSeen > b.lastSeen ? -1 : 1
  );
  
  const sortedJobs = Object.values(jobs).sort((a, b) => 
    a.status === 'processing' && b.status !== 'processing' ? -1 : 
    a.status !== 'processing' && b.status === 'processing' ? 1 : 
    (a.submitted_at || 0) > (b.submitted_at || 0) ? -1 : 1
  );
  
  return (
    <div className="max-w-6xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-4">System Monitor</h1>
        <p className="text-gray-600 mb-6">
          View detailed information about workers, jobs, and system status.
        </p>
      </div>
      
      {/* System Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="bg-white p-6 rounded-lg shadow-md">
          <h2 className="text-lg font-semibold mb-2">Workers</h2>
          <div className="flex justify-between items-center">
            <span className="text-3xl font-bold">{isClient ? stats.workers.total : '-'}</span>
            <div className="flex flex-col text-sm text-gray-500">
              <span>Active: {isClient ? stats.workers.active : '-'}</span>
              <span>Idle: {isClient ? stats.workers.idle : '-'}</span>
              <span>Busy: {isClient ? stats.workers.busy : '-'}</span>
            </div>
          </div>
        </div>
        
        <div className="bg-white p-6 rounded-lg shadow-md">
          <h2 className="text-lg font-semibold mb-2">Jobs</h2>
          <div className="flex justify-between items-center">
            <span className="text-3xl font-bold">{isClient ? stats.jobs.total : '-'}</span>
            <div className="flex flex-col text-sm text-gray-500">
              <span>Pending: {isClient ? stats.jobs.pending : '-'}</span>
              <span>Processing: {isClient ? stats.jobs.processing : '-'}</span>
              <span>Completed: {isClient ? stats.jobs.completed : '-'}</span>
              <span>Failed: {isClient ? stats.jobs.failed : '-'}</span>
            </div>
          </div>
        </div>
        
        <div className="bg-white p-6 rounded-lg shadow-md">
          <h2 className="text-lg font-semibold mb-2">Clients</h2>
          <div className="flex justify-between items-center">
            <span className="text-3xl font-bold">{isClient ? stats.clients.total : '-'}</span>
          </div>
        </div>
      </div>
      
      {/* Workers Section */}
      <div className="mb-8">
        <h2 className="text-2xl font-semibold mb-4">Workers</h2>
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    ID
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Last Seen
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Capabilities
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {isClient && sortedWorkers.length > 0 ? (
                  sortedWorkers.map((worker) => (
                    <tr key={worker.id}>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                        {worker.id}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm">
                        <span className={`px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${
                          worker.status === 'active' ? 'bg-green-100 text-green-800' : 
                          worker.status === 'idle' ? 'bg-yellow-100 text-yellow-800' : 
                          'bg-gray-100 text-gray-800'
                        }`}>
                          {worker.status}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {formatRelativeTime(worker.lastSeen)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {worker.capabilities ? Object.keys(worker.capabilities).join(', ') : 'None'}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} className="px-6 py-4 text-center text-sm text-gray-500">
                      No workers found
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      
      {/* Jobs Section */}
      <div className="mb-8">
        <h2 className="text-2xl font-semibold mb-4">Jobs</h2>
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    ID
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Type
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Worker
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Submitted
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {isClient && sortedJobs.length > 0 ? (
                  sortedJobs.map((job) => (
                    <tr key={job.id}>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                        {job.id}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {job.type}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm">
                        <span className={`px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${
                          job.status === 'completed' ? 'bg-green-100 text-green-800' : 
                          job.status === 'processing' ? 'bg-blue-100 text-blue-800' : 
                          job.status === 'pending' ? 'bg-yellow-100 text-yellow-800' : 
                          job.status === 'failed' ? 'bg-red-100 text-red-800' : 
                          'bg-gray-100 text-gray-800'
                        }`}>
                          {job.status}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {job.worker_id || 'None'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {job.submitted_at ? formatRelativeTime(job.submitted_at) : 'Unknown'}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="px-6 py-4 text-center text-sm text-gray-500">
                      No jobs found
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      
      {/* System Map */}
      <div className="mb-8">
        <h2 className="text-2xl font-semibold mb-4">System Map</h2>
        <div className="bg-white p-6 rounded-lg shadow-md">
          <div className="flex justify-center">
            <div className="w-full max-w-3xl h-64 border border-gray-200 rounded-lg flex items-center justify-center">
              <p className="text-gray-500">System map visualization will be implemented here</p>
            </div>
          </div>
        </div>
      </div>
      
      {/* Raw Message Data Display */}
      <div className="mb-8">
        <h2 className="text-2xl font-semibold mb-4">Raw Message Data</h2>
        <div className="bg-white p-6 rounded-lg shadow-md">
          <div className="overflow-auto max-h-96">
            <pre className="text-xs">{lastMessage ? JSON.stringify(lastMessage, null, 2) : 'No messages received yet'}</pre>
          </div>
        </div>
      </div>
    </div>
  );
}
