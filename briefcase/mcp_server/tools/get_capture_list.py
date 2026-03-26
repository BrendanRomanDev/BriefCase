"""MCP Tool: get_capture_list - Query inbox items."""

import logging
from typing import Optional
from briefcase.mcp_server.database import get_db_connection, get_inbox_items

logger = logging.getLogger(__name__)


async def get_capture_list(
    initiative_slug: Optional[str] = None,
    status: Optional[str] = None
) -> dict:
    """Query inbox items with optional filters."""
    try:
        conn = get_db_connection()
        items = get_inbox_items(conn, initiative_slug=initiative_slug, status=status)
        conn.close()

        return {
            "status": "success",
            "count": len(items),
            "items": items,
            "filters": {
                "initiative": initiative_slug,
                "status": status
            }
        }
    except Exception as e:
        logger.error(f"get_capture_list error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "get_capture_list"
TOOL_DESCRIPTION = "Query inbox items. Filter by initiative and/or status. Excludes completed items by default."
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "initiative_slug": {"type": "string",
                           "description": "Filter by initiative slug"},
        "status": {"type": "string",
                   "description": "Filter by status (capture, scheduled, completed)"}
    }
}

__all__ = ['get_capture_list', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
