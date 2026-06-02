#!/usr/bin/env python3
"""
Hybrid DBMS - Web Interface
Run this file to start the web server
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from web_app.app import app

if __name__ == '__main__':
    print("=" * 60)
    print("🎓 Hybrid DBMS - Web Interface")
    print("=" * 60)
    print("\nStarting web server...")
    print("Open your browser and go to: http://localhost:5000")
    print("\nPress Ctrl+C to stop the server\n")
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=5000)