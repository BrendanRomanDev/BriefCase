"""MCP Tool: save_conversation_notes - Save session context for continuity."""

import logging
from typing import Optional
from briefcase.mcp_server.database import get_db_connection, save_conversation_note

logger = logging.getLogger(__name__)


async def save_conversation_notes(
    summary: str,
    next_intentions: Optional[str] = None,
    topics: Optional[list] = None
) -> dict:
    """Save session context for continuity. Called at end of conversations."""
    try:
        conn = get_db_connection()
        note_id = save_conversation_note(conn, summary, next_intentions, topics)
        conn.close()

        return {
            "status": "success",
            "message": "Session notes saved",
            "note_id": note_id
        }
    except Exception as e:
        logger.error(f"save_conversation_notes error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "save_conversation_notes"
TOOL_DESCRIPTION = "Save session context for continuity. Call at end of conversations."
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "Summary of what happened this session"},
        "next_intentions": {"type": "string", "description": "What to pick up next session"},
        "topics": {"type": "array", "items": {"type": "string"},
                   "description": "Key topics discussed"}
    },
    "required": ["summary"]
}

__all__ = ['save_conversation_notes', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
