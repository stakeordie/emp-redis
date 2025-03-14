'use client';

import { useEffect, useState } from 'react';
import { useAppStore } from '@/lib/store';
import { getWebSocketManager } from '@/lib/websocket';

/**
 * Connections page for the Redis Monitor application
 * 
 * This page displays connection status indicators for various system components,
 * starting with a test for "Client can connect to hub".
 */
export default function ConnectionsPage() {
  const { 
    connectionTests,
    connectionStates,
    connect,
    disconnect,
    isConnected,
    areAllConnected
  } = useAppStore();
  const [isClient, setIsClient] = useState(false);
  
  // Initialize WebSocket connection on client-side only
  useEffect(() => {
    setIsClient(true);
  }, []);
  
  // Function to establish connections
  const establishConnections = async () => {
    await connect();
  };

  // Function to disconnect all connections
  const disconnectAll = () => {
    disconnect();
  };
  
  // Function to check connection status
  const checkConnectionStatus = (type: 'client' | 'monitor') => {
    return isConnected(type);
  };
  
  // Function to get status color based on test status
  const getStatusColor = (status: 'untested' | 'success' | 'failure') => {
    switch (status) {
      case 'success':
        return 'bg-green-500';
      case 'failure':
        return 'bg-red-500';
      default:
        return 'bg-gray-400';
    }
  };
  
  // Function to get status text based on test status
  const getStatusText = (status: 'untested' | 'success' | 'failure') => {
    switch (status) {
      case 'success':
        return 'Success';
      case 'failure':
        return 'Failed';
      default:
        return 'Not Tested';
    }
  };
  
  // Get the connection tests
  const clientHubTest = connectionTests?.['client-hub-connection'];
  const monitorHubTest = connectionTests?.['monitor-hub-connection'];
  
  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-4">Connection Monitor</h1>
        <p className="text-gray-600 mb-6">
          Monitor the status of various connections in the Redis system.
          Run tests to verify connectivity between components.
        </p>
      </div>
      
      {/* Connection Tests */}
      <div className="bg-white p-6 rounded-lg shadow-md mb-8">
        <h2 className="text-xl font-semibold mb-4">Connection Tests</h2>
        <p className="text-gray-600 mb-4">
          These tests verify that your application can connect to the Redis Hub. 
          The tests will connect briefly and then disconnect automatically.
        </p>
        
        <div className="space-y-4">
          {/* Client Connection Test */}
          {isClient && clientHubTest && (
            <div className="border rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center space-x-3">
                  <div className={`w-4 h-4 rounded-full ${getStatusColor(clientHubTest.status)}`}></div>
                  <h3 className="font-medium">{clientHubTest.name}</h3>
                </div>
                <span className="text-sm text-gray-500">
                  {getStatusText(clientHubTest.status)}
                </span>
              </div>
              
              {clientHubTest.lastTested && (
                <div className="text-sm text-gray-500 mb-2">
                  Last tested: {new Date(clientHubTest.lastTested).toLocaleString()}
                </div>
              )}
              
              {clientHubTest.errorMessage && (
                <div className="text-sm text-red-500 mb-2">
                  Error: {clientHubTest.errorMessage}
                </div>
              )}
              
              <button
                onClick={establishConnections}
                className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors"
              >
                Connect
              </button>
            </div>
          )}

          {/* Monitor Connection Test */}
          {isClient && monitorHubTest && (
            <div className="border rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center space-x-3">
                  <div className={`w-4 h-4 rounded-full ${getStatusColor(monitorHubTest.status)}`}></div>
                  <h3 className="font-medium">{monitorHubTest.name}</h3>
                </div>
                <span className="text-sm text-gray-500">
                  {getStatusText(monitorHubTest.status)}
                </span>
              </div>
              
              {monitorHubTest.lastTested && (
                <div className="text-sm text-gray-500 mb-2">
                  Last tested: {new Date(monitorHubTest.lastTested).toLocaleString()}
                </div>
              )}
              
              {monitorHubTest.errorMessage && (
                <div className="text-sm text-red-500 mb-2">
                  Error: {monitorHubTest.errorMessage}
                </div>
              )}
              
              <button
                onClick={disconnectAll}
                className="px-4 py-2 bg-red-500 text-white rounded hover:bg-red-600 transition-colors"
              >
                Disconnect
              </button>
            </div>
          )}
          
          {!isClient && (
            <div className="text-gray-500">Loading connection tests...</div>
          )}
        </div>
      </div>
      

      
      {/* Connection Status */}
      <div className="bg-white p-6 rounded-lg shadow-md">
        <h2 className="text-xl font-semibold mb-4">Connection Status</h2>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          {/* Client Connection Status */}
          <div className="border rounded-lg p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center space-x-3">
                <div className={`w-4 h-4 rounded-full ${connectionStates.client.connected ? 'bg-green-500' : 'bg-red-500'}`}></div>
                <h3 className="font-medium">Client Connection</h3>
              </div>
              <span className="text-sm text-gray-500">
                {connectionStates.client.status}
              </span>
            </div>
          </div>
          
          {/* Monitor Connection Status */}
          <div className="border rounded-lg p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center space-x-3">
                <div className={`w-4 h-4 rounded-full ${connectionStates.monitor.connected ? 'bg-green-500' : 'bg-red-500'}`}></div>
                <h3 className="font-medium">Monitor Connection</h3>
              </div>
              <span className="text-sm text-gray-500">
                {connectionStates.monitor.status}
              </span>
            </div>
          </div>
        </div>
        
        <p className="text-gray-600">
          Use the Connect and Disconnect buttons above to manage both client and monitor connections simultaneously.
          When connected as a monitor, you'll receive real-time updates about the Redis system, including workers, jobs, and clients.
        </p>
        <p className="text-gray-600 mt-2">
          The connection tests above are for diagnostic purposes only and will automatically disconnect after testing.
        </p>
      </div>
    </div>
  );
}
