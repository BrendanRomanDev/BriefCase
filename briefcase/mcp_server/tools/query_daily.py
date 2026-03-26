"""MCP Tool: query_daily - Look up a specific day's plan."""

import logging
from briefcase.mcp_server.database import get_db_connection, get_daily

logger = logging.getLogger(__name__)


async def query_daily(date: str) -> dict:
    """Look up a specific day's plan from the dailies table."""
    try:
        conn = get_db_connection()
        daily = get_daily(conn, date)
        conn.close()

        if not daily:
            return {"status": "success", "message": f"No plan found for {date}", "daily": None}

        return {"status": "success", "daily": daily}
    except Exception as e:
        logger.error(f"query_daily error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "query_daily"
TOOL_DESCRIPTION = "Look up a specific day's task plan."
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "date": {"type": "string", "description": "Date to look up (YYYY-MM-DD)"}
    },
    "required": ["date"]
}

__all__ = ['query_daily', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
