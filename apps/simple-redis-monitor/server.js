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
  let urlParts = filePath.split('?');
  filePath = urlParts[0];
  
  // [2025-05-19T18:02:00-04:00] Handle API routes
  if (filePath.startsWith('/api/')) {
    // Set CORS headers to allow requests from any origin
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    
    // Handle OPTIONS requests for CORS preflight
    if (req.method === 'OPTIONS') {
      res.writeHead(204);
      res.end();
      return;
    }
    
    // Handle force retry API endpoint
    if (filePath === '/api/force_retry' && req.method === 'POST') {
      let body = '';
      req.on('data', chunk => {
        body += chunk.toString();
      });
      
      req.on('end', () => {
        try {
          const data = JSON.parse(body);
          const jobId = data.job_id;
          
          if (!jobId) {
            res.writeHead(400, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ success: false, error: 'Missing job_id parameter' }));
            return;
          }
          
          console.log(`[2025-05-19T18:02:00-04:00] Force retry requested for job: ${jobId}`);
          
          // In a real implementation, this would call the Redis service to force retry the job
          // For now, we'll just return a success response
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ 
            success: true, 
            message: `Force retry initiated for job ${jobId}` 
          }));
        } catch (error) {
          console.error('Error processing force retry request:', error);
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ success: false, error: 'Invalid request format' }));
        }
      });
      
      return;
    }
    
    // If we reach here, the API endpoint was not found
    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ success: false, error: 'API endpoint not found' }));
    return;
  }
  
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