/**
 * Simple HTTP Server for Redis Monitor
 * 
 * This file contains a basic HTTP server to serve the Redis Monitor HTML and JavaScript files.
 * Written in plain JavaScript as per the Types Philosophy.
 */

const http = require('http');
const fs = require('fs');
const path = require('path');

// Define the port to run the server on
const PORT = 3030;

// Map file extensions to MIME types
const MIME_TYPES = {
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon'
};

/**
 * Create a simple HTTP server
 */
const server = http.createServer((req, res) => {
  // Log the request
  console.log(`${new Date().toISOString()} - ${req.method} ${req.url}`);
  
  // Parse the URL to get the pathname
  let filePath = req.url;
  
  // If the URL is '/', serve the index.html file
  if (filePath === '/') {
    filePath = '/index.html';
  }
  
  // Get the full path to the requested file
  const fullPath = path.join(__dirname, filePath);
  
  // Get the file extension
  const extname = path.extname(fullPath);
  
  // Set the content type based on the file extension
  const contentType = MIME_TYPES[extname] || 'application/octet-stream';
  
  // Read the file
  fs.readFile(fullPath, (err, content) => {
    if (err) {
      // If the file doesn't exist, return a 404 error
      if (err.code === 'ENOENT') {
        console.error(`File not found: ${fullPath}`);
        res.writeHead(404, { 'Content-Type': 'text/html' });
        res.end('<h1>404 Not Found</h1><p>The requested resource was not found on this server.</p>');
      } else {
        // For other errors, return a 500 error
        console.error(`Server error: ${err.code}`);
        res.writeHead(500, { 'Content-Type': 'text/html' });
        res.end('<h1>500 Internal Server Error</h1><p>Sorry, there was a problem on our end.</p>');
      }
    } else {
      // If the file exists, serve it with the appropriate content type
      res.writeHead(200, { 'Content-Type': contentType });
      res.end(content);
    }
  });
});

// Start the server
server.listen(PORT, () => {
  console.log(`Server running at http://localhost:${PORT}/`);
  console.log(`Press Ctrl+C to stop the server`);
});