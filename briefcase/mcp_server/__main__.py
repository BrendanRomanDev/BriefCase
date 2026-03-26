"""Entry point for running the BriefCase MCP server as a module.

Usage: python -m briefcase.mcp_server
"""

import asyncio
from briefcase.mcp_server.server import main

if __name__ == "__main__":
    asyncio.run(main())
