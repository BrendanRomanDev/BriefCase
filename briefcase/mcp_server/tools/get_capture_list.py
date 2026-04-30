"""MCP Tool: get_capture_list - Query inbox items."""

import logging
from typing import Optional
from briefcase.mcp_server.database import get_db_connection, get_inbox_items

logger = logging.getLogger(__name__)


async def get_capture_list(
    initiative_slug: Optional[str] = None,
    status: Optional[str] = None,
    target_week: Optional[str] = None,
    tags: Optional[list] = None,
) -> dict:
    """Query inbox items with optional filters.

    `tags` is a list - returns items whose tags include ALL given tags
    (AND match). Useful for finding items flagged for downstream work
    (e.g. tags=['needs_code_context']).
    """
    try:
        conn = get_db_connection()
        items = get_inbox_items(conn, initiative_slug=initiative_slug,
                                status=status, target_week=target_week,
                                tags=tags)
        conn.close()

        return {
            "status": "success",
            "count": len(items),
            "items": items,
            "filters": {
                "initiative": initiative_slug,
                "status": status,
                "target_week": target_week,
                "tags": tags,
            }
        }
    except Exception as e:
        logger.error(f"get_capture_list error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "get_capture_list"
TOOL_DESCRIPTION = (
    "Query inbox items. Filter by initiative, status, target_week, and/or "
    "tags. Excludes completed items by default. Items returned with tags "
    "decoded as a list. Use tags=['needs_code_context'] to find items "
    "flagged for Thriveworks-repo follow-up work."
)
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "initiative_slug": {"type": "string",
                           "description": "Filter by initiative slug"},
        "status": {"type": "string",
                   "description": "Filter by status (capture, scheduled, completed)"},
        "target_week": {"type": "string",
                        "description": "Filter by target week (e.g. '2026-W15')"},
        "tags": {"type": "array", "items": {"type": "string"},
                 "description": "Filter to items whose tags include ALL given tags. e.g. ['needs_code_context'] for items flagged for code follow-up."}
    }
}

__all__ = ['get_capture_list', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
