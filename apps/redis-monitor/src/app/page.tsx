'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useAppStore } from '@/lib/store';
import { getWebSocketManager } from '@/lib/websocket';

/**
 * Home page for the Redis Monitor application
 * 
 * This page serves as the landing page and provides quick access to the main features
 * of the Redis Monitor application.
 */
export default function Home() {
  const { stats, setConnectionState } = useAppStore();
  const [isMonitor, setIsMonitor] = useState(false);
  console.log('🔍 Dashboard: Monitor-side state:', isMonitor);
  // Initialize client-side state only
  useEffect(() => {
    setIsMonitor(true);
    
    // Just monitor connection status without initiating a connection
    const checkConnectionStatus = () => {
      const monitorManager = getWebSocketManager('monitor');
      
      console.log("MMANAGER: ", monitorManager)
      console.log("Stats: ", stats)

      // Only update the UI state based on the current connection status
      setConnectionState('monitor', { 
        connected: monitorManager.isConnected(),
        status: monitorManager.isConnected() ? 'connected' : 'disconnected'
      });
    };
    
    const intervalId = setInterval(checkConnectionStatus, 1000);


    return () => {
      clearInterval(intervalId);
    };
  }, [setConnectionState]);
  
  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-4">Redis Monitor Dashboard</h1>
        <p className="text-gray-600 mb-6">
          Welcome to the Redis Monitor application. This tool allows you to monitor and debug
          the EmProps Redis system in real-time.
        </p>
      </div>
      
      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="bg-white p-6 rounded-lg shadow-md">
          <h2 className="text-lg font-semibold mb-2">Workers</h2>
          <div className="flex justify-between items-center">
            <span className="text-3xl font-bold">{isMonitor ? stats.workers.total : '-'}</span>
            <div className="flex flex-col text-sm text-gray-500">
              <span>Active: {isMonitor ? stats.workers.active : '-'}</span>
              <span>Idle: {isMonitor ? stats.workers.idle : '-'}</span>
            </div>
          </div>
        </div>
        
        <div className="bg-white p-6 rounded-lg shadow-md">
          <h2 className="text-lg font-semibold mb-2">Jobs</h2>
          <div className="flex justify-between items-center">
            <span className="text-3xl font-bold">{isMonitor ? stats.jobs.total : '-'}</span>
            <div className="flex flex-col text-sm text-gray-500">
              <span>Pending: {isMonitor ? stats.jobs.pending : '-'}</span>
              <span>Processing: {isMonitor ? stats.jobs.processing : '-'}</span>
              <span>Completed: {isMonitor ? stats.jobs.completed : '-'}</span>
            </div>
          </div>
        </div>
        
        <div className="bg-white p-6 rounded-lg shadow-md">
          <h2 className="text-lg font-semibold mb-2">Clients</h2>
          <div className="flex justify-between items-center">
            <span className="text-3xl font-bold">{isMonitor ? stats.clients.total : '-'}</span>
          </div>
        </div>
      </div>
      
      {/* Quick Links */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Link href="/dashboard" className="block p-6 bg-blue-50 hover:bg-blue-100 rounded-lg border border-blue-200 transition-colors">
          <h2 className="text-xl font-semibold mb-2 text-blue-700">System Monitor</h2>
          <p className="text-blue-600 mb-4">
            View detailed system statistics, worker status, and job information.
          </p>
          <span className="text-blue-700 font-medium">Open System Monitor →</span>
        </Link>
        
        <Link href="/ws-debug" className="block p-6 bg-purple-50 hover:bg-purple-100 rounded-lg border border-purple-200 transition-colors">
          <h2 className="text-xl font-semibold mb-2 text-purple-700">WebSocket Debug</h2>
          <p className="text-purple-600 mb-4">
            Monitor WebSocket connections and messages in real-time.
          </p>
          <span className="text-purple-700 font-medium">Open WebSocket Debug →</span>
        </Link>
        
        <Link href="/connections" className="block p-6 bg-green-50 hover:bg-green-100 rounded-lg border border-green-200 transition-colors">
          <h2 className="text-xl font-semibold mb-2 text-green-700">Connection Monitor</h2>
          <p className="text-green-600 mb-4">
            Check the status of system connections and run connectivity tests.
          </p>
          <span className="text-green-700 font-medium">Open Connection Monitor →</span>
        </Link>
      </div>
    </div>
  );
}
