"""MCP Tool: file_meeting_notes - File meeting notes in Obsidian and propose actions."""

import logging
from datetime import datetime
from typing import Optional
from briefcase.mcp_server.database import get_db_connection, get_initiative_by_slug
from briefcase.mcp_server.obsidian import (
    build_meeting_note, write_file, meeting_note_path, read_file
)

logger = logging.getLogger(__name__)


async def file_meeting_notes(
    content: str,
    initiative_slug: Optional[str] = None,
    title: Optional[str] = None,
    date: Optional[str] = None,
    attendees: Optional[list] = None,
    tags: Optional[list] = None,
    summary: Optional[str] = None,
    key_decisions: Optional[list] = None,
    action_items: Optional[list] = None
) -> dict:
    """File meeting notes in Obsidian, return summary and proposed actions.

    The agent should generate summary, key_decisions, and action_items from the
    raw content before calling this tool. The tool files the note and returns
    the proposed actions for conversational triage — it does NOT auto-create tasks.
    """
    try:
        if not date:
            date = datetime.now().strftime('%Y-%m-%d')

        if not title:
            title = f"Meeting Notes — {date}"

        # Validate initiative if provided
        initiative_name = None
        if initiative_slug:
            conn = get_db_connection()
            initiative = get_initiative_by_slug(conn, initiative_slug)
            conn.close()
            if not initiative:
                return {"status": "error", "message": f"Initiative '{initiative_slug}' not found"}
            initiative_name = initiative['name']

        # Build the formatted note
        note_content = build_meeting_note(
            title=title,
            date=date,
            initiative_slug=initiative_slug,
            attendees=attendees or [],
            tags=tags or [],
            summary=summary or '',
            key_decisions=key_decisions or [],
            action_items=action_items or [],
            raw_notes=content
        )

        # Determine file path and write
        file_path = meeting_note_path(initiative_slug, date, title)
        full_path = write_file(file_path, note_content)

        result = {
            "status": "success",
            "message": f"Meeting notes filed to {file_path}",
            "file_path": file_path,
            "full_path": full_path,
            "initiative": initiative_slug,
            "initiative_name": initiative_name,
            "date": date,
            "title": title,
        }

        if summary:
            result["summary"] = summary
        if key_decisions:
            result["key_decisions"] = key_decisions
        if action_items:
            result["proposed_actions"] = action_items
            result["note"] = ("These are PROPOSED actions extracted from the meeting notes. "
                            "Ask the user which ones to act on — do NOT auto-create tasks.")

        return result

    except Exception as e:
        logger.error(f"file_meeting_notes error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "file_meeting_notes"
TOOL_DESCRIPTION = "File meeting notes in Obsidian with frontmatter, summary, and proposed actions. Does NOT auto-create tasks — returns proposed actions for conversational triage."
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "content": {"type": "string", "description": "Raw meeting notes or transcript to file"},
        "initiative_slug": {"type": "string", "description": "Initiative slug to file under (files to Meetings/general/ if omitted)"},
        "title": {"type": "string", "description": "Meeting title (auto-generated from date if omitted)"},
        "date": {"type": "string", "description": "Meeting date YYYY-MM-DD (defaults to today)"},
        "attendees": {"type": "array", "items": {"type": "string"}, "description": "List of attendees"},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags for categorization"},
        "summary": {"type": "string", "description": "Agent-generated summary of the meeting"},
        "key_decisions": {"type": "array", "items": {"type": "string"}, "description": "Key decisions extracted from notes"},
        "action_items": {"type": "array", "items": {"type": "string"}, "description": "Proposed action items extracted from notes (presented to user, NOT auto-created)"}
    },
    "required": ["content"]
}

__all__ = ['file_meeting_notes', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
