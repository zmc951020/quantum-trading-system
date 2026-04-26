const fs = require('fs');
const path = require('path');

function file_read({ file_path }) {
  try {
    // Resolve the absolute path
    const absolutePath = path.resolve(file_path);
    
    // Check if the file exists
    if (!fs.existsSync(absolutePath)) {
      return { error: 'File not found' };
    }
    
    // Check if it's a file (not a directory)
    if (!fs.statSync(absolutePath).isFile()) {
      return { error: 'Path is not a file' };
    }
    
    // Read the file content
    const content = fs.readFileSync(absolutePath, 'utf8');
    const size = content.length;
    
    return {
      content,
      size,
      path: absolutePath
    };
  } catch (error) {
    return { error: error.message };
  }
}

// Test the file_read function
console.log('Testing file_read function...');

// Test with README.md in MemX-Ollama directory
const result = file_read({ file_path: 'MemX-Ollama/README.md' });

if (result.error) {
  console.error('Error:', result.error);
} else {
  console.log('Success!');
  console.log('File path:', result.path);
  console.log('File size:', result.size, 'bytes');
  console.log('File content:');
  console.log(result.content);
}
