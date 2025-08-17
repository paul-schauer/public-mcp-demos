#!/usr/bin/env python3
"""
Setup script for USDA FDC MCP Server
"""

import os
import sys
import subprocess
import json
import platform

def install_requirements():
    """Install required packages."""
    print("Installing required packages...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✓ Requirements installed successfully")
        return True
    except subprocess.CalledProcessError:
        print("✗ Failed to install requirements")
        return False

def check_api_key():
    """Check if API key is set."""
    api_key = os.getenv("USDA_FDC_API_KEY")
    if api_key:
        print("✓ USDA_FDC_API_KEY environment variable is set")
        return True
    else:
        print("✗ USDA_FDC_API_KEY environment variable is not set")
        print("  Please get your free API key from: https://fdc.nal.usda.gov/api-key-signup.html")
        return False

def get_claude_config_path():
    """Get the Claude Desktop configuration file path."""
    system = platform.system()
    if system == "Darwin":  # macOS
        return os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json")
    elif system == "Windows":
        return os.path.expandvars(r"%APPDATA%\Claude\claude_desktop_config.json")
    else:  # Linux and others
        return os.path.expanduser("~/.config/claude/claude_desktop_config.json")

def create_claude_config():
    """Help create Claude Desktop configuration."""
    config_path = get_claude_config_path()
    script_path = os.path.abspath("usda_fdc_mcp_server.py")
    api_key = os.getenv("USDA_FDC_API_KEY", "your_api_key_here")
    
    config = {
        "mcpServers": {
            "usda-fdc": {
                "command": "python",
                "args": [script_path],
                "env": {
                    "USDA_FDC_API_KEY": api_key
                }
            }
        }
    }
    
    print(f"\nClaude Desktop configuration should be added to:")
    print(f"  {config_path}")
    print(f"\nSuggested configuration:")
    print(json.dumps(config, indent=2))
    
    if api_key == "your_api_key_here":
        print("\n⚠️  Remember to replace 'your_api_key_here' with your actual API key!")

def main():
    """Main setup function."""
    print("USDA Food Data Central MCP Server Setup")
    print("=" * 40)
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("✗ Python 3.8 or higher is required")
        sys.exit(1)
    print(f"✓ Python {sys.version.split()[0]} is compatible")
    
    # Install requirements
    if not install_requirements():
        sys.exit(1)
    
    # Check API key
    api_key_set = check_api_key()
    
    # Make script executable on Unix-like systems
    if platform.system() != "Windows":
        try:
            os.chmod("usda_fdc_mcp_server.py", 0o755)
            print("✓ Made server script executable")
        except OSError:
            print("⚠️  Could not make server script executable")
    
    # Show Claude configuration
    create_claude_config()
    
    print("\n" + "=" * 40)
    if api_key_set:
        print("✓ Setup complete! You can now add this server to Claude Desktop.")
        print("\nTo test the server, run:")
        print("  python test_server.py")
    else:
        print("⚠️  Setup almost complete!")
        print("   1. Get your API key from: https://fdc.nal.usda.gov/api-key-signup.html")
        print("   2. Set the USDA_FDC_API_KEY environment variable")
        print("   3. Add the server configuration to Claude Desktop")

if __name__ == "__main__":
    main()