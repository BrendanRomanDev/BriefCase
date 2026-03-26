"""MCP Tool: manage_initiative_members - Add, remove, or list team members."""

import logging
from typing import Optional
from briefcase.mcp_server.database import (
    get_db_connection, get_initiative_by_slug,
    add_initiative_member, remove_initiative_member, get_initiative_members
)

logger = logging.getLogger(__name__)


async def manage_initiative_members(
    action: str,
    initiative_slug: str,
    name: Optional[str] = None,
    role: Optional[str] = None
) -> dict:
    """Add, remove, or list team members on an initiative."""
    try:
        conn = get_db_connection()
        initiative = get_initiative_by_slug(conn, initiative_slug)

        if not initiative:
            conn.close()
            return {"status": "error", "message": f"Initiative '{initiative_slug}' not found"}

        initiative_id = initiative['id']

        if action == "add":
            if not name:
                conn.close()
                return {"status": "error", "message": "name is required for add"}

            member_id = add_initiative_member(conn, initiative_id, name, role)
            conn.close()
            return {
                "status": "success",
                "message": f"Added {name} to {initiative_slug}",
                "member_id": member_id
            }

        elif action == "remove":
            if not name:
                conn.close()
                return {"status": "error", "message": "name is required for remove"}

            found = remove_initiative_member(conn, initiative_id, name)
            conn.close()

            if not found:
                return {"status": "error", "message": f"{name} not found on {initiative_slug}"}
            return {"status": "success", "message": f"Removed {name} from {initiative_slug}"}

        elif action == "list":
            members = get_initiative_members(conn, initiative_id)
            conn.close()
            return {
                "status": "success",
                "initiative": initiative_slug,
                "count": len(members),
                "members": members
            }

        else:
            conn.close()
            return {"status": "error", "message": f"Unknown action: {action}. Use add, remove, or list."}

    except Exception as e:
        logger.error(f"manage_initiative_members error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "manage_initiative_members"
TOOL_DESCRIPTION = "Add, remove, or list team members on an initiative."
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["add", "remove", "list"],
                   "description": "Action to perform"},
        "initiative_slug": {"type": "string", "description": "Initiative slug"},
        "name": {"type": "string", "description": "Team member name (required for add/remove)"},
        "role": {"type": "string", "description": "Role on the initiative (e.g., Developer, QA, Stakeholder)"}
    },
    "required": ["action", "initiative_slug"]
}

__all__ = ['manage_initiative_members', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
