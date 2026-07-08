"""MCP Tool: update_external_ref - Update mutable fields on an existing ref.

Primarily how the briefing flow keeps a ticket's assignee + status_line current
without deleting and re-adding the ref. Also handles re-titling (label) or
correcting a URL.
"""

import logging
from typing import Optional

from briefcase.mcp_server.database import (
    get_db_connection, update_external_ref as db_update_ref
)
from briefcase.mcp_server.refs import derive_ref_url

logger = logging.getLogger(__name__)


async def update_external_ref(
    ref_id: int,
    assignee: Optional[str] = None,
    status_line: Optional[str] = None,
    label: Optional[str] = None,
    ref_url: Optional[str] = None,
) -> dict:
    """Update assignee / status_line / label / ref_url on an existing external
    ref. Only the fields you pass change. To clear a field explicitly (e.g.
    un-assign a ticket), pass an empty string ''.

    Use this during a briefing update when a ticket's owner or open-loop status
    changed — e.g. "coverage config schema handed to Nishant" →
    update_external_ref(ref_id, assignee='Nishant', status_line='handed off, in progress').
    """
    try:
        conn = get_db_connection()
        kwargs = {}
        if assignee is not None:
            kwargs["assignee"] = assignee
        if status_line is not None:
            kwargs["status_line"] = status_line
        if label is not None:
            kwargs["label"] = label
        if ref_url is not None:
            kwargs["ref_url"] = ref_url

        if not kwargs:
            conn.close()
            return {"status": "error", "message": "Nothing to update — pass at least one field."}

        updated = db_update_ref(conn, ref_id, **kwargs)
        conn.close()

        if not updated:
            return {"status": "error", "message": f"external_ref #{ref_id} not found or no change."}
        return {
            "status": "success",
            "ref_id": ref_id,
            "updated_fields": list(kwargs.keys()),
        }
    except Exception as e:
        logger.error(f"update_external_ref error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "update_external_ref"
TOOL_DESCRIPTION = (
    "Update mutable fields (assignee, status_line, label, ref_url) on an existing "
    "external ref by its ref_id. The briefing flow's way to keep a ticket's owner and "
    "one-line status current without re-adding it. Pass '' to clear a field (e.g. "
    "un-assign). Only fields you pass change."
)
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "ref_id": {
            "type": "integer",
            "description": "ID of the external_ref to update (from list_external_refs)."
        },
        "assignee": {
            "type": "string",
            "description": "New owner. Pass '' to un-assign, 'unassigned' to mark explicitly unowned."
        },
        "status_line": {
            "type": "string",
            "description": "New one-line open-loop/status note for the briefing. '' clears it."
        },
        "label": {
            "type": "string",
            "description": "New human-readable label (e.g. corrected ticket title)."
        },
        "ref_url": {
            "type": "string",
            "description": "New explicit URL."
        },
    },
    "required": ["ref_id"],
}

__all__ = ['update_external_ref', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
