#!/usr/bin/env python3
"""
Simple launcher script for Prompt Studio
"""
import subprocess
import sys
import os
from pathlib import Path

def check_python_version():
    """Check if Python version is compatible"""
    if sys.version_info < (3, 11):
        print("Error: Python 3.11 or higher is required")
        print(f"Current version: {sys.version}")
        sys.exit(1)

def install_dependencies():
    """Install required dependencies if needed"""
    try:
        import PySide6
        import sqlmodel
        import jinja2
        import httpx
        import keyring
        print("All dependencies are already installed.")
        return True
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Installing dependencies...")
        
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
            ])
            print("Dependencies installed successfully.")
            return True
        except subprocess.CalledProcessError:
            print("Failed to install dependencies.")
            print("Please install them manually with: pip install -r requirements.txt")
            return False

def main():
    """Main launcher function"""
    print("🚀 Starting Prompt Studio...")
    
    # Change to script directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    # Check Python version
    check_python_version()
    
    # Install dependencies if needed
    if not install_dependencies():
        sys.exit(1)
    
    # Launch the application
    try:
        from main import main as app_main
        app_main()
    except KeyboardInterrupt:
        print("\nShutdown requested by user.")
    except Exception as e:
        print(f"Error starting application: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
