"""MCP Tool: clear_triage_queue - Delete resolved items from the queue."""

import logging
from briefcase.mcp_server.database import (
    get_db_connection, clear_resolved_triage_items
)

logger = logging.getLogger(__name__)


async def clear_triage_queue() -> dict:
    """Delete all resolved triage queue items. Pending items are untouched."""
    try:
        conn = get_db_connection()
        deleted = clear_resolved_triage_items(conn)
        conn.close()

        return {
            "status": "success",
            "deleted": deleted,
            "message": f"Cleared {deleted} resolved triage item(s)"
        }
    except Exception as e:
        logger.error(f"clear_triage_queue error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "clear_triage_queue"
TOOL_DESCRIPTION = (
    "Delete all resolved triage queue items (history cleanup). Pending "
    "items are never touched. Only call when the user explicitly asks to "
    "clean up the queue."
)
TOOL_SCHEMA = {
    "type": "object",
    "properties": {}
}

__all__ = ['clear_triage_queue', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
