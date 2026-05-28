"""MCP Tool: get_triage_queue - List pending captures awaiting triage."""

import logging
from typing import Optional
from briefcase.mcp_server.database import get_db_connection, get_triage_items

logger = logging.getLogger(__name__)


async def get_triage_queue(
    status: Optional[str] = "pending",
    limit: Optional[int] = None
) -> dict:
    """List items in the triage queue.

    The queue holds raw captures from the Chrome extension (web clips,
    chat messages, etc.) until Kit walks through them 1x1 and promotes
    them into inbox items, initiatives, vault notes, or discards.
    """
    try:
        conn = get_db_connection()
        items = get_triage_items(
            conn, status=status, limit=limit, attach_children=True
        )
        conn.close()

        return {
            "status": "success",
            "count": len(items),
            "items": items,
            "filters": {"status": status, "limit": limit}
        }
    except Exception as e:
        logger.error(f"get_triage_queue error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "get_triage_queue"
TOOL_DESCRIPTION = (
    "List captures awaiting triage. Defaults to pending items only. "
    "Each item carries its source (e.g. 'google_chat'), a permalink, the "
    "captured content, and optional metadata (sender, channel, thread preview). "
    "Use at conversation start or when the user asks 'what's in the queue?' "
    "Walk through items 1x1 with the user to decide: brain dump, initiative, "
    "thrivenote, daily note, or discard - then call triage_item to resolve. "
    "Attached captures appear nested in `children: [...]` under their parent; "
    "triage the composite together (resolving the parent resolves all children)."
)
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["pending", "resolved"],
            "description": "Filter by status. Default 'pending'."
        },
        "limit": {
            "type": "integer",
            "description": "Optional max number of items to return."
        }
    }
}

__all__ = ['get_triage_queue', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
