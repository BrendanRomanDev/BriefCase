"""MCP Tool: plan_daily - Create or update a daily task plan."""

import logging
from typing import Optional
from briefcase.mcp_server.database import get_db_connection, upsert_daily

logger = logging.getLogger(__name__)


async def plan_daily(date: str, tasks: list, notes: Optional[str] = None) -> dict:
    """Create or update a daily plan. Stores tasks only - calendar events are
    handled by the agent via Google Calendar MCP separately."""
    try:
        conn = get_db_connection()
        daily_id = upsert_daily(conn, date, tasks, notes)
        conn.close()

        return {
            "status": "success",
            "message": f"Daily plan saved for {date}",
            "daily_id": daily_id,
            "task_count": len(tasks)
        }
    except Exception as e:
        logger.error(f"plan_daily error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "plan_daily"
TOOL_DESCRIPTION = "Create or update a daily task plan. Stores tasks only - calendar events are handled by the agent separately via Google Calendar MCP."
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "date": {"type": "string", "description": "Date for the plan (YYYY-MM-DD)"},
        "tasks": {
            "type": "array",
            "items": {
                "oneOf": [
                    {"type": "string"},
                    {"type": "object", "properties": {
                        "title": {"type": "string"},
                        "type": {"type": "string"},
                        "initiative": {"type": "string"},
                        "completed": {"type": "boolean"}
                    }}
                ]
            },
            "description": "Array of task items (strings or objects with title/type/initiative)"
        },
        "notes": {"type": "string", "description": "Optional notes for the day"}
    },
    "required": ["date", "tasks"]
}

__all__ = ['plan_daily', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
