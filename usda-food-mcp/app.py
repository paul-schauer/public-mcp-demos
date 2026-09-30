#!/usr/bin/env python3
"""Entrypoint wrapper for Railpack / hosting platforms.

This file simply delegates to the main() function in
`usda_fdc_mcp_server.py` so the platform can discover a
standard start file named `app.py`.
"""
from usda_fdc_mcp_server import main


if __name__ == "__main__":
    main()
