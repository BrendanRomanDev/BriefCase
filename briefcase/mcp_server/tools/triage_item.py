"""MCP Tool: triage_item - Resolve a triage queue item into its destination."""

import logging
from typing import Optional
from briefcase.mcp_server.database import (
    get_db_connection,
    get_triage_item,
    resolve_triage_item,
    create_inbox_item,
    create_initiative,
    get_initiative_by_slug,
)
from briefcase.mcp_server.obsidian import scaffold_initiative_folder

logger = logging.getLogger(__name__)


VALID_ACTIONS = {"brain_dump", "initiative", "thrivenote", "daily_note",
                 "discard", "mark_resolved"}


async def triage_item(
    item_id: int,
    action: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    complexity: Optional[int] = None,
    urgency: Optional[int] = None,
    initiative_slug: Optional[str] = None,
    target_week: Optional[str] = None,
    initiative_name: Optional[str] = None,
    initiative_deadline: Optional[str] = None,
    initiative_tags: Optional[list] = None,
    initiative_repo_path: Optional[str] = None,
    scaffold_obsidian_folder: bool = True,
    resolution_note: Optional[str] = None
) -> dict:
    """Resolve a triage queue item by routing it into its destination.

    Actions:
      - brain_dump: create an inbox item. Source URL + metadata from the
        queue item are carried onto the inbox item.
      - initiative: create a new initiative. Source URL + metadata are
        carried onto the initiative row. Use initiative_slug as the slug
        and initiative_name/_deadline/_tags/_repo_path for details.
      - thrivenote: mark the queue item resolved — the agent is expected
        to have filed the note to the vault separately (and must embed
        the source_url in the markdown body per the global thrive-notes
        rule). Use resolution_note to record what was filed.
      - daily_note: mark the queue item resolved — the agent is expected
        to have called plan_daily separately to add this to a day's notes.
      - discard: mark resolved with no further action.
      - mark_resolved: generic "I handled this externally" — optionally
        pass resolution_note.
    """
    try:
        if action not in VALID_ACTIONS:
            return {
                "status": "error",
                "message": f"Unknown action '{action}'. Valid: {sorted(VALID_ACTIONS)}"
            }

        conn = get_db_connection()
        queue_item = get_triage_item(conn, item_id)
        if not queue_item:
            conn.close()
            return {"status": "error", "message": f"Triage item #{item_id} not found"}
        if queue_item['status'] != 'pending':
            conn.close()
            return {
                "status": "error",
                "message": f"Triage item #{item_id} already resolved as '{queue_item.get('resolution')}'"
            }

        result = {"status": "success", "triage_item_id": item_id, "action": action}

        if action == "brain_dump":
            if not title:
                conn.close()
                return {"status": "error", "message": "title is required for brain_dump action"}

            initiative_id = None
            if initiative_slug:
                initiative = get_initiative_by_slug(conn, initiative_slug)
                if not initiative:
                    conn.close()
                    return {"status": "error", "message": f"Initiative '{initiative_slug}' not found"}
                initiative_id = initiative['id']

            inbox_id = create_inbox_item(
                conn,
                title=title,
                description=description,
                complexity=complexity,
                urgency=urgency,
                initiative_id=initiative_id,
                target_week=target_week,
                source=queue_item.get('source'),
                source_url=queue_item.get('source_url'),
                source_metadata=queue_item.get('metadata'),
            )
            result["inbox_item_id"] = inbox_id
            result["message"] = f"Brain dumped: {title}"

        elif action == "initiative":
            if not initiative_name or not initiative_slug:
                conn.close()
                return {
                    "status": "error",
                    "message": "initiative_name and initiative_slug are required for initiative action"
                }
            existing = get_initiative_by_slug(conn, initiative_slug)
            if existing:
                conn.close()
                return {"status": "error", "message": f"Initiative '{initiative_slug}' already exists"}

            initiative_id = create_initiative(
                conn,
                name=initiative_name,
                slug=initiative_slug,
                description=description,
                deadline=initiative_deadline,
                tags=initiative_tags,
                repo_path=initiative_repo_path,
                source=queue_item.get('source'),
                source_url=queue_item.get('source_url'),
                source_metadata=queue_item.get('metadata'),
            )
            result["initiative_id"] = initiative_id
            result["initiative_slug"] = initiative_slug
            result["message"] = f"Created initiative: {initiative_name}"

            if scaffold_obsidian_folder:
                project_dir = scaffold_initiative_folder(
                    initiative_slug, initiative_name, description
                )
                result["obsidian_folder"] = str(project_dir)

        elif action == "thrivenote":
            result["message"] = "Marked as filed to ThriveNotes"
            if resolution_note:
                result["resolution_note"] = resolution_note

        elif action == "daily_note":
            result["message"] = "Marked as added to a daily"
            if resolution_note:
                result["resolution_note"] = resolution_note

        elif action == "discard":
            result["message"] = "Discarded"

        elif action == "mark_resolved":
            result["message"] = "Marked resolved"
            if resolution_note:
                result["resolution_note"] = resolution_note

        resolution_label = "discarded" if action == "discard" else action
        resolved = resolve_triage_item(conn, item_id, resolution_label)
        conn.close()

        if not resolved:
            return {
                "status": "error",
                "message": f"Failed to mark triage item #{item_id} as resolved"
            }

        return result

    except Exception as e:
        logger.error(f"triage_item error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "triage_item"
TOOL_DESCRIPTION = (
    "Resolve a triage queue item by routing it into a destination: "
    "brain_dump (new inbox item), initiative (new project), thrivenote "
    "(agent filed externally), daily_note (agent added to a daily), "
    "discard, or mark_resolved. Source URL + metadata are automatically "
    "carried onto brain_dump and initiative destinations. Always walks "
    "the user through the decision — do not call without their input."
)
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "item_id": {"type": "integer", "description": "Triage queue item ID"},
        "action": {
            "type": "string",
            "enum": sorted(list(VALID_ACTIONS)),
            "description": "How to resolve this item"
        },
        "title": {"type": "string", "description": "Title for brain_dump action"},
        "description": {"type": "string", "description": "Description for brain_dump or initiative"},
        "complexity": {"type": "integer", "minimum": 1, "maximum": 3},
        "urgency": {"type": "integer", "minimum": 1, "maximum": 3},
        "initiative_slug": {
            "type": "string",
            "description": "For brain_dump: link to this existing initiative. For initiative: slug of the new initiative."
        },
        "target_week": {
            "type": "string",
            "description": "ISO week for brain_dump action (e.g. '2026-W15')"
        },
        "initiative_name": {"type": "string", "description": "Required for initiative action"},
        "initiative_deadline": {"type": "string", "description": "YYYY-MM-DD deadline for new initiative"},
        "initiative_tags": {"type": "array", "items": {"type": "string"}},
        "initiative_repo_path": {"type": "string", "description": "Path to git repo for new initiative"},
        "scaffold_obsidian_folder": {
            "type": "boolean",
            "description": "On initiative action, also create Projects/<slug>/ in the Obsidian vault. Defaults to true."
        },
        "resolution_note": {
            "type": "string",
            "description": "Freeform note about how the item was resolved (e.g. the path of a filed thrivenote)"
        }
    },
    "required": ["item_id", "action"]
}

__all__ = ['triage_item', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
