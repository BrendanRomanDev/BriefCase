"""MCP Tool: get_recent_activity - Recent dailies and conversation notes."""

import logging
from datetime import datetime, timedelta, UTC
from briefcase.mcp_server.database import (
    get_db_connection, get_dailies_range, get_recent_conversation_notes
)

logger = logging.getLogger(__name__)


async def get_recent_activity(days: int = 3) -> dict:
    """Last N days of daily plans and conversation notes."""
    try:
        conn = get_db_connection()
        now = datetime.now(UTC)
        start_date = (now - timedelta(days=days)).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")

        dailies = get_dailies_range(conn, start_date, end_date)
        notes = get_recent_conversation_notes(conn, days=days)
        conn.close()

        return {
            "status": "success",
            "period": f"Last {days} days ({start_date} to {end_date})",
            "dailies": dailies,
            "conversation_notes": notes
        }
    except Exception as e:
        logger.error(f"get_recent_activity error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "get_recent_activity"
TOOL_DESCRIPTION = "Get recent daily plans and conversation notes for continuity."
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "days": {"type": "integer", "default": 3,
                 "description": "Number of days to look back (default 3)"}
    }
}

__all__ = ['get_recent_activity', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
