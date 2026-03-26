"""MCP Tool: brain_dump - Capture a task to the inbox."""

import logging
from typing import Optional
from briefcase.mcp_server.database import get_db_connection, create_inbox_item, get_initiative_by_slug

logger = logging.getLogger(__name__)


async def brain_dump(
    title: str,
    description: Optional[str] = None,
    complexity: Optional[int] = None,
    urgency: Optional[int] = None,
    initiative_slug: Optional[str] = None
) -> dict:
    """Capture a brain dump item to the inbox."""
    try:
        if complexity is not None and not (1 <= complexity <= 3):
            return {"status": "error", "message": "Complexity must be 1-3"}
        if urgency is not None and not (1 <= urgency <= 3):
            return {"status": "error", "message": "Urgency must be 1-3"}

        initiative_id = None
        if initiative_slug:
            conn = get_db_connection()
            initiative = get_initiative_by_slug(conn, initiative_slug)
            conn.close()
            if not initiative:
                return {"status": "error", "message": f"Initiative '{initiative_slug}' not found"}
            initiative_id = initiative['id']

        conn = get_db_connection()
        item_id = create_inbox_item(
            conn, title=title, description=description,
            complexity=complexity, urgency=urgency,
            initiative_id=initiative_id
        )
        conn.close()

        msg = f"Captured: {title}"
        if initiative_slug:
            msg += f" (linked to {initiative_slug})"

        return {
            "status": "success",
            "message": msg,
            "item_id": item_id,
            "initiative": initiative_slug
        }
    except Exception as e:
        logger.error(f"brain_dump error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "brain_dump"
TOOL_DESCRIPTION = "Capture a task to the inbox with optional complexity, urgency, and initiative linkage."
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Task title"},
        "description": {"type": "string", "description": "Optional longer description"},
        "complexity": {"type": "integer", "minimum": 1, "maximum": 3,
                       "description": "Task complexity (1=simple, 2=moderate, 3=complex)"},
        "urgency": {"type": "integer", "minimum": 1, "maximum": 3,
                    "description": "Task urgency (1=someday, 2=this week, 3=ASAP)"},
        "initiative_slug": {"type": "string",
                           "description": "Slug of initiative to link this task to"}
    },
    "required": ["title"]
}

__all__ = ['brain_dump', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
