'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAppStore } from '@/lib/store';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { useEffect, useState } from 'react';

// Utility function for merging class names
function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Navigation component for the Redis Monitor application
 */
export function Navigation() {
  const pathname = usePathname();
  const { 
    connectionStates,
    connect,
    disconnect,
    isConnected,
    areAllConnected
  } = useAppStore();
  const [isClient, setIsClient] = useState(false);
  
  // Initialize client-side state
  useEffect(() => {
    setIsClient(true);
  }, []);
  
  return (
    <nav className="bg-gray-800 text-white p-4">
      <div className="container mx-auto flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <h1 className="text-xl font-bold">Redis Monitor</h1>
          <div className="flex items-center space-x-2">
            <div className="flex items-center">
              <div className={cn(
                "w-3 h-3 rounded-full mr-1",
                connectionStates.client.connected ? 'bg-green-500' : 
                connectionStates.client.status === 'connecting' ? 'bg-yellow-500' : 'bg-red-500'
              )}></div>
              <span className="text-xs">Client</span>
            </div>
            <div className="flex items-center">
              <div className={cn(
                "w-3 h-3 rounded-full mr-1",
                connectionStates.monitor.connected ? 'bg-green-500' : 
                connectionStates.monitor.status === 'connecting' ? 'bg-yellow-500' : 'bg-red-500'
              )}></div>
              <span className="text-xs">Monitor</span>
            </div>
          </div>
        </div>
        
        {isClient && (
          <div className="flex items-center space-x-2">
            <button
              onClick={() => connect()}
              disabled={areAllConnected()}
              className={cn(
                "px-2 py-1 rounded text-sm",
                areAllConnected() ? 
                  "bg-gray-600 cursor-not-allowed" : 
                  "bg-blue-600 hover:bg-blue-700"
              )}
            >
              Connect All
            </button>
            <button
              onClick={() => disconnect()}
              disabled={!isConnected('client') && !isConnected('monitor')}
              className={cn(
                "px-2 py-1 rounded text-sm",
                !isConnected('client') && !isConnected('monitor') ? 
                  "bg-gray-600 cursor-not-allowed" : 
                  "bg-red-600 hover:bg-red-700"
              )}
            >
              Disconnect All
            </button>
          </div>
        )}
        
        <div className="flex space-x-4">
          <Link 
            href="/" 
            className={cn(
              "px-3 py-2 rounded hover:bg-gray-700",
              pathname === '/' && "bg-gray-700"
            )}
          >
            Dashboard
          </Link>
          <Link 
            href="/dashboard" 
            className={cn(
              "px-3 py-2 rounded hover:bg-gray-700",
              pathname === '/dashboard' && "bg-gray-700"
            )}
          >
            System Monitor
          </Link>
          <Link 
            href="/ws-debug" 
            className={cn(
              "px-3 py-2 rounded hover:bg-gray-700",
              pathname === '/ws-debug' && "bg-gray-700"
            )}
          >
            WebSocket Debug
          </Link>
          <Link 
            href="/connections" 
            className={cn(
              "px-3 py-2 rounded hover:bg-gray-700",
              pathname === '/connections' && "bg-gray-700"
            )}
          >
            Connections
          </Link>
        </div>
      </div>
    </nav>
  );
}
