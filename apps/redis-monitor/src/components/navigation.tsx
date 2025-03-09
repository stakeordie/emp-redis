'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAppStore } from '@/lib/store';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

// Utility function for merging class names
function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Navigation component for the Redis Monitor application
 */
export function Navigation() {
  const pathname = usePathname();
  const { connectionStatus } = useAppStore();
  
  return (
    <nav className="bg-gray-800 text-white p-4">
      <div className="container mx-auto flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <h1 className="text-xl font-bold">Redis Monitor</h1>
          <div className={cn(
            "w-3 h-3 rounded-full",
            connectionStatus === 'connected' ? 'bg-green-500' : 
            connectionStatus === 'connecting' ? 'bg-yellow-500' : 'bg-red-500'
          )}></div>
        </div>
        
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
        </div>
      </div>
    </nav>
  );
}
