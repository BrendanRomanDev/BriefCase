#!/bin/bash
# Restart the BriefCase MCP server
# Useful after code changes

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Restarting BriefCase MCP server..."
echo "Project dir: $PROJECT_DIR"

# Kill any existing server process
pkill -f "briefcase.mcp_server.server" 2>/dev/null && echo "Stopped existing server" || echo "No existing server running"

echo "Server will be started by Claude Code on next tool call."
echo "If running standalone, use: cd $PROJECT_DIR && python -m briefcase.mcp_server.server"
