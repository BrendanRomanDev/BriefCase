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
    initiative_slug: Optional[str] = None,
    target_week: Optional[str] = None,
    source: Optional[str] = None,
    source_url: Optional[str] = None,
    source_metadata: Optional[dict] = None
) -> dict:
    """Capture a brain dump item to the inbox."""
    try:
        if complexity is not None and not (1 <= complexity <= 3):
            return {"status": "error", "message": "Complexity must be 1-3"}
        if urgency is not None and not (1 <= urgency <= 3):
            return {"status": "error", "message": "Urgency must be 1-3"}
        if target_week is not None:
            import re
            if not re.match(r'^\d{4}-W(0[1-9]|[1-4]\d|5[0-3])$', target_week):
                return {"status": "error", "message": "target_week must be ISO format like '2026-W15'"}

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
            initiative_id=initiative_id, target_week=target_week,
            source=source, source_url=source_url,
            source_metadata=source_metadata
        )
        conn.close()

        msg = f"Captured: {title}"
        if initiative_slug:
            msg += f" (linked to {initiative_slug})"
        if target_week:
            msg += f" (targeted for {target_week})"
        if source:
            msg += f" [source: {source}]"

        return {
            "status": "success",
            "message": msg,
            "item_id": item_id,
            "initiative": initiative_slug,
            "target_week": target_week,
            "source": source,
            "source_url": source_url
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
                           "description": "Slug of initiative to link this task to"},
        "target_week": {"type": "string",
                        "description": "ISO week to target this item for (e.g. '2026-W15'). Use when the item should get done in a specific week but doesn't have an exact day yet."},
        "source": {"type": "string",
                   "description": "Where this captured item came from (e.g. 'google_chat', 'web_clip', 'slack'). Preserved so Kit can render a link back to the origin."},
        "source_url": {"type": "string",
                       "description": "Permalink back to the original source (e.g. the Google Chat message link)."},
        "source_metadata": {"type": "object",
                            "description": "Free-form metadata about the source (sender, channel, timestamp, thread preview, etc.). Stored as JSON."}
    },
    "required": ["title"]
}

__all__ = ['brain_dump', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
