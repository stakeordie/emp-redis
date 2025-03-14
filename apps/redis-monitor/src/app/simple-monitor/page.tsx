'use client';

import { useEffect, useState } from 'react';
import { useAppStore } from '@/lib/store';
import { getWebSocketManager } from '@/lib/websocket';
import { Message, MessageType, getMessageData } from '@/lib/types/messages';

/**
 * Simple Monitor Page
 * 
 * A minimal page that only shows the number of workers to focus on reactivity issues
 */
export default function SimpleMonitorPage() {
  // Get the stats from the store
  const { stats, updateStats } = useAppStore();
  
  // Track if we're on the client side
  const [isClient, setIsClient] = useState(false);
  
  // Track the raw message for debugging
  const [lastMessage, setLastMessage] = useState<any>(null);
  
  // Track connection status
  const [isConnected, setIsConnected] = useState(false);
  
  // Local state for worker counts
  const [workerCounts, setWorkerCounts] = useState({
    total: 0,
    active: 0,
    idle: 0,
    busy: 0
  });
  
  // Force re-render counter
  const [refreshCounter, setRefreshCounter] = useState(0);
  
  // Function to force a re-render
  const forceRefresh = () => {
    setRefreshCounter(prev => prev + 1);
    console.log('🔍 SimpleMonitor: Manual refresh triggered');
  };
  
  // Initialize WebSocket connection on client-side only
  useEffect(() => {
    // Set client-side flag
    setIsClient(true);
    console.log('🔍 SimpleMonitor: Component mounted, initializing WebSocket connection');
    
    // Get the monitor WebSocket manager
    const monitorManager = getWebSocketManager('monitor', {
      endpoint: '/ws/monitor', // Make sure we're using the monitor endpoint
      onOpen: (event) => {
        console.log('🔍 SimpleMonitor: WebSocket connection opened', event);
        setIsConnected(true);
      },
      onClose: (event) => {
        console.log('🔍 SimpleMonitor: WebSocket connection closed', event);
        setIsConnected(false);
      },
      onError: (event) => {
        console.log('🔍 SimpleMonitor: WebSocket connection error', event);
        setIsConnected(false);
      },
      onMessage: (message) => {
        console.log('🔍 SimpleMonitor: Received message:', message.type);
      }
    });
    
    // Connect to the WebSocket server
    console.log('🔍 SimpleMonitor: Connecting to monitor WebSocket...');
    monitorManager.connect();
    
    // Check connection status periodically
    const checkConnectionInterval = setInterval(() => {
      const connected = monitorManager.isConnected();
      setIsConnected(connected);
      console.log('🔍 SimpleMonitor: Monitor connection status:', connected);
    }, 2000);
    
    // Define handler for STATS_BROADCAST messages
    const handleStatsBroadcast = (message: Message) => {
      console.log('🔍 SimpleMonitor: Received STATS_BROADCAST message:', message.type);
      
      // Parse the message data
      const data = getMessageData(message);
      console.log('🔍 SimpleMonitor: Parsed message data:', JSON.stringify(data, null, 2));
      
      // Store the raw message for debugging
      setLastMessage(data);
      
      // Extract worker stats from the message
      if (data.system && data.system.workers) {
        console.log('🔍 SimpleMonitor: Found system.workers data:', data.system.workers);
        
        // Update both local state and store
        const newWorkerCounts = {
          total: data.system.workers.total || 0,
          active: data.system.workers.active || 0,
          idle: data.system.workers.idle || 0,
          busy: data.system.workers.busy || 0,
        };
        
        setWorkerCounts(newWorkerCounts);
        
        // Also update the store
        updateStats({
          workers: newWorkerCounts
        });
        
        console.log('🔍 SimpleMonitor: Updated worker counts:', newWorkerCounts);
      } else if (data.workers && typeof data.workers === 'object') {
        // If we have direct workers data, count them
        const workerCount = Object.keys(data.workers).length;
        console.log('🔍 SimpleMonitor: Found direct workers data, count:', workerCount);
        
        // Count workers by status
        const activeWorkers = Object.values(data.workers).filter((w: any) => 
          w.status === 'active' || w.connection_status === 'active'
        ).length;
        
        const idleWorkers = Object.values(data.workers).filter((w: any) => 
          w.status === 'idle' || w.connection_status === 'idle'
        ).length;
        
        const busyWorkers = Object.values(data.workers).filter((w: any) => 
          w.status === 'busy' || w.connection_status === 'busy'
        ).length;
        
        // Update both local state and store
        const newWorkerCounts = {
          total: workerCount,
          active: activeWorkers,
          idle: idleWorkers,
          busy: busyWorkers,
        };
        
        setWorkerCounts(newWorkerCounts);
        
        // Also update the store
        updateStats({
          workers: newWorkerCounts
        });
        
        console.log('🔍 SimpleMonitor: Updated worker counts:', newWorkerCounts);
      } else {
        console.log('🔍 SimpleMonitor: No worker data found in message');
      }
    };
    
    // Register the message handler
    console.log('🔍 SimpleMonitor: Registering STATS_BROADCAST handler');
    monitorManager.on(MessageType.STATS_BROADCAST, handleStatsBroadcast);
    
    // Clean up on unmount
    return () => {
      console.log('🔍 SimpleMonitor: Component unmounting, cleaning up');
      clearInterval(checkConnectionInterval);
      monitorManager.off(MessageType.STATS_BROADCAST, handleStatsBroadcast);
      monitorManager.disconnect();
    };
  }, [updateStats, refreshCounter]); // Include refreshCounter to allow manual refresh
  
  return (
    <div className="max-w-6xl mx-auto p-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-4">Simple Worker Monitor</h1>
        <p className="text-gray-600 mb-6">
          A minimal page that only shows the number of workers to focus on reactivity issues.
        </p>
      </div>
      
      {/* Connection Status */}
      <div className="mb-8">
        <div className={`p-4 rounded-lg ${isConnected ? 'bg-green-100' : 'bg-red-100'}`}>
          <p className="font-semibold">
            WebSocket Status: {isConnected ? 'Connected' : 'Disconnected'}
          </p>
          <button 
            onClick={forceRefresh} 
            className="mt-2 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
          >
            Force Refresh
          </button>
        </div>
      </div>
      
      {/* Worker Count Display - Using Local State */}
      <div className="mb-8">
        <div className="bg-white p-8 rounded-lg shadow-md">
          <h2 className="text-2xl font-semibold mb-4">Worker Count (Local State)</h2>
          <div className="text-center">
            <div className="text-6xl font-bold mb-4">
              {isClient ? workerCounts.total : '-'}
            </div>
            <div className="grid grid-cols-3 gap-4 text-center">
              <div className="p-4 bg-blue-100 rounded-lg">
                <p className="text-sm text-gray-600">Active</p>
                <p className="text-2xl font-semibold">{isClient ? workerCounts.active : '-'}</p>
              </div>
              <div className="p-4 bg-yellow-100 rounded-lg">
                <p className="text-sm text-gray-600">Idle</p>
                <p className="text-2xl font-semibold">{isClient ? workerCounts.idle : '-'}</p>
              </div>
              <div className="p-4 bg-purple-100 rounded-lg">
                <p className="text-sm text-gray-600">Busy</p>
                <p className="text-2xl font-semibold">{isClient ? workerCounts.busy : '-'}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      {/* Worker Count Display - Using Store */}
      <div className="mb-8">
        <div className="bg-white p-8 rounded-lg shadow-md">
          <h2 className="text-2xl font-semibold mb-4">Worker Count (Store)</h2>
          <div className="text-center">
            <div className="text-6xl font-bold mb-4">
              {isClient ? stats.workers.total : '-'}
            </div>
            <div className="grid grid-cols-3 gap-4 text-center">
              <div className="p-4 bg-blue-100 rounded-lg">
                <p className="text-sm text-gray-600">Active</p>
                <p className="text-2xl font-semibold">{isClient ? stats.workers.active : '-'}</p>
              </div>
              <div className="p-4 bg-yellow-100 rounded-lg">
                <p className="text-sm text-gray-600">Idle</p>
                <p className="text-2xl font-semibold">{isClient ? stats.workers.idle : '-'}</p>
              </div>
              <div className="p-4 bg-purple-100 rounded-lg">
                <p className="text-sm text-gray-600">Busy</p>
                <p className="text-2xl font-semibold">{isClient ? stats.workers.busy : '-'}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      {/* Raw Message Data (for debugging) */}
      <div className="mb-8">
        <h2 className="text-2xl font-semibold mb-4">Raw Message Data</h2>
        <div className="bg-white p-6 rounded-lg shadow-md">
          <div className="overflow-auto max-h-96">
            <pre className="text-xs whitespace-pre-wrap">
              {lastMessage ? JSON.stringify(lastMessage, null, 2) : 'No messages received yet'}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}
