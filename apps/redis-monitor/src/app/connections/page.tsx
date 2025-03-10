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
  const { connectionTests, testClientConnection } = useAppStore();
  const [isClient, setIsClient] = useState(false);
  
  // Initialize WebSocket connection on client-side only
  useEffect(() => {
    setIsClient(true);
  }, []);
  
  // Function to run the client connection test
  const runClientConnectionTest = async () => {
    await testClientConnection();
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
  
  // Get the client-hub connection test
  const clientHubTest = connectionTests?.['client-hub-connection'];
  
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
        
        <div className="space-y-4">
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
                onClick={runClientConnectionTest}
                className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors"
              >
                Run Test
              </button>
            </div>
          )}
          
          {!isClient && (
            <div className="text-gray-500">Loading connection tests...</div>
          )}
        </div>
      </div>
      
      {/* Future Connection Tests */}
      <div className="bg-white p-6 rounded-lg shadow-md">
        <h2 className="text-xl font-semibold mb-4">Future Connection Tests</h2>
        <p className="text-gray-600">
          Additional connection tests will be added here as the system expands.
          These may include tests for Redis connections, worker connections, and more.
        </p>
      </div>
    </div>
  );
}
