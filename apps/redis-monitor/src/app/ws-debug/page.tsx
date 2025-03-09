'use client';

import { useEffect, useState, useRef } from 'react';
import { useAppStore } from '@/lib/store';
import { getWebSocketManager } from '@/lib/websocket';
import { Message, MessageType } from '@core/client-types/messages';
import { formatTimestamp, generateId } from '@/lib/utils';
import { getMessageData } from '@/lib/types/monitor-messages';
/**
 * Client-side only component for rendering JSON data
 */
const JsonTreeViewer = ({ data }: { data: any }) => {
  const [Component, setComponent] = useState<any>(null);

  useEffect(() => {
    // Import JSONTree only on the client side
    import('react-json-tree').then((mod) => {
      setComponent(() => mod.default);
    });
  }, []);

  // JSON theme for the message viewer
  const jsonTheme = {
    scheme: 'monokai',
    base00: '#272822',
    base01: '#383830',
    base02: '#49483e',
    base03: '#75715e',
    base04: '#a59f85',
    base05: '#f8f8f2',
    base06: '#f5f4f1',
    base07: '#f9f8f5',
    base08: '#f92672',
    base09: '#fd971f',
    base0A: '#f4bf75',
    base0B: '#a6e22e',
    base0C: '#a1efe4',
    base0D: '#66d9ef',
    base0E: '#ae81ff',
    base0F: '#cc6633'
  };

  if (!Component) {
    return <div className="p-2 text-gray-500">Loading JSON viewer...</div>;
  }

  return (
    <Component
      data={data}
      theme={jsonTheme}
      invertTheme={false}
      shouldExpandNode={() => true}
    />
  );
};

/**
 * WebSocket Debug Page
 * 
 * This page provides tools for monitoring and debugging WebSocket connections
 * and messages in real-time.
 */
export default function WebSocketDebugPage() {
  const { 
    messageLog, 
    addMessageLogEntry, 
    clearMessageLog, 
    setConnectionStatus 
  } = useAppStore();
  
  const [isClient, setIsClient] = useState(false);
  const [selectedMessage, setSelectedMessage] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<MessageType | 'all'>('all');
  const [customMessage, setCustomMessage] = useState('');
  const wsManagerRef = useRef<any>(null);
  
  // Initialize WebSocket connection on client-side only
  useEffect(() => {
    setIsClient(true);
    
    const wsManager = getWebSocketManager({
      onMessage: (message: Message) => {
        // Add received message to log
        addMessageLogEntry({
          id: generateId(),
          timestamp: Date.now() / 1000,
          direction: 'received' as const,
          message: message
        });
      }
    });
    
    wsManagerRef.current = wsManager;
    wsManager.connect();
    
    // Update connection status
    const checkConnection = () => {
      setConnectionStatus(wsManager.isConnected() ? 'connected' : 'disconnected');
    };
    
    const intervalId = setInterval(checkConnection, 1000);
    
    return () => {
      clearInterval(intervalId);
      wsManager.disconnect();
    };
  }, [addMessageLogEntry, setConnectionStatus]);
  
  // Get the selected message details
  const selectedMessageDetails = selectedMessage 
    ? messageLog.find(entry => entry.id === selectedMessage) 
    : null;
  
  // Filter messages by type
  const filteredMessages = filterType === 'all' 
    ? messageLog 
    : messageLog.filter(entry => entry.message.type === filterType);
  
  // Handle sending a custom message
  const handleSendMessage = () => {
    try {
      const message = JSON.parse(customMessage);
      
      if (wsManagerRef.current && wsManagerRef.current.isConnected()) {
        // Add sent message to log
        const messageEntry = {
          id: generateId(),
          timestamp: Date.now() / 1000,
          direction: 'sent' as const,
          message: message
        };
        
        addMessageLogEntry(messageEntry);
        wsManagerRef.current.send(message);
        
        // Clear the custom message input
        setCustomMessage('');
      }
    } catch (error) {
      console.error('Error sending message:', error);
      alert('Invalid JSON format');
    }
  };
  
  // JSON theme moved to JsonTreeViewer component
  
  return (
    <div className="max-w-6xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-4">WebSocket Debug Tool</h1>
        <p className="text-gray-600 mb-6">
          Monitor WebSocket connections and messages in real-time.
        </p>
      </div>
      
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Message List */}
        <div className="lg:col-span-2">
          <div className="bg-white rounded-lg shadow-md overflow-hidden">
            <div className="p-4 border-b border-gray-200 flex items-center justify-between">
              <h2 className="text-lg font-semibold">Message Log</h2>
              <div className="flex space-x-2">
                <select
                  className="text-sm border border-gray-300 rounded px-2 py-1"
                  value={filterType}
                  onChange={(e) => setFilterType(e.target.value as MessageType | 'all')}
                >
                  <option value="all">All Messages</option>
                  {Object.values(MessageType).map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </select>
                <button
                  className="text-sm bg-red-50 text-red-600 px-2 py-1 rounded hover:bg-red-100"
                  onClick={clearMessageLog}
                >
                  Clear
                </button>
              </div>
            </div>
            <div className="h-[500px] overflow-y-auto">
              {isClient && filteredMessages.length > 0 ? (
                <div className="divide-y divide-gray-100">
                  {filteredMessages.map((entry) => (
                    <div
                      key={entry.id}
                      className={`p-3 cursor-pointer hover:bg-gray-50 ${
                        selectedMessage === entry.id ? 'bg-blue-50' : ''
                      }`}
                      onClick={() => setSelectedMessage(entry.id)}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                          entry.direction === 'received' ? 'bg-green-100 text-green-800' : 'bg-blue-100 text-blue-800'
                        }`}>
                          {entry.direction === 'received' ? 'Received' : 'Sent'}
                        </span>
                        <span className="text-xs text-gray-500">
                          {formatTimestamp(entry.timestamp)}
                        </span>
                      </div>
                      <div className="text-sm font-medium">
                        {entry.message.type}
                      </div>
                      <div className="text-xs text-gray-500 truncate">
                        {JSON.stringify(getMessageData(entry.message))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex items-center justify-center h-full">
                  <p className="text-gray-500">No messages</p>
                </div>
              )}
            </div>
          </div>
        </div>
        
        {/* Message Details */}
        <div className="lg:col-span-3">
          <div className="bg-white rounded-lg shadow-md h-full">
            <div className="p-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold">Message Details</h2>
            </div>
            <div className="p-4 h-[500px] overflow-y-auto">
              {selectedMessageDetails ? (
                <div>
                  <div className="mb-4">
                    <div className="flex justify-between items-center mb-2">
                      <div className="text-sm font-medium">
                        {selectedMessageDetails.direction === 'received' ? 'Received' : 'Sent'} Message
                      </div>
                      <div className="text-xs text-gray-500">
                        {formatTimestamp(selectedMessageDetails.timestamp)}
                      </div>
                    </div>
                    <div className="text-xs text-gray-500">
                      ID: {selectedMessageDetails.id}
                    </div>
                  </div>
                  
                  <div className="mb-4">
                    <div className="text-sm font-medium mb-1">Type</div>
                    <div className="text-sm bg-gray-50 p-2 rounded">
                      {selectedMessageDetails.message.type}
                    </div>
                  </div>
                  
                  <div>
                    <div className="text-sm font-medium mb-1">Data</div>
                    <div className="text-sm bg-gray-50 p-2 rounded overflow-x-auto">
                      {/* Use client-side only JsonTreeViewer component */}
                      <JsonTreeViewer data={getMessageData(selectedMessageDetails.message)} />
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-center h-full">
                  <p className="text-gray-500">Select a message to view details</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
      
      {/* Send Message Form */}
      <div className="mt-6">
        <div className="bg-white rounded-lg shadow-md p-4">
          <h2 className="text-lg font-semibold mb-4">Send Custom Message</h2>
          <div className="mb-4">
            <textarea
              className="w-full h-32 p-2 border border-gray-300 rounded font-mono text-sm"
              placeholder="Enter JSON message..."
              value={customMessage}
              onChange={(e) => setCustomMessage(e.target.value)}
            ></textarea>
          </div>
          <div className="flex justify-between">
            <div>
              <button
                className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
                onClick={handleSendMessage}
                disabled={!isClient || !wsManagerRef.current?.isConnected()}
              >
                Send Message
              </button>
            </div>
            <div className="text-sm text-gray-500">
              Example: {"{ \"type\": \"PING\", \"data\": { \"timestamp\": 1625097600 } }"}
            </div>
          </div>
        </div>
      </div>
      
      {/* Connection Status */}
      <div className="mt-6">
        <div className="bg-white rounded-lg shadow-md p-4">
          <h2 className="text-lg font-semibold mb-2">Connection Status</h2>
          <div className="flex items-center">
            <div className={`w-3 h-3 rounded-full mr-2 ${
              wsManagerRef.current?.isConnected() ? 'bg-green-500' : 'bg-red-500'
            }`}></div>
            <span className="text-sm">
              {wsManagerRef.current?.isConnected() ? 'Connected' : 'Disconnected'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
