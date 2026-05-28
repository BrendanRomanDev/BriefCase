"""MCP Tool: claim_triage_item - Atomically lock a queue item to one agent."""

import logging

from briefcase.mcp_server.database import (
    get_db_connection, claim_triage_item as db_claim_triage_item,
    get_triage_item,
)

logger = logging.getLogger(__name__)


async def claim_triage_item(item_id: int, claimed_by: str) -> dict:
    """Atomically claim a pending triage queue item, flipping it to
    'in_progress' and stamping `claimed_at` + `claimed_by`.

    Atomicity: the underlying SQL UPDATE matches WHERE status='pending', so
    if another agent claimed first, this returns ok=False (failed_reason=
    'already_claimed') and we don't overwrite their claim.

    `claimed_by` is a short label so other agents (or you in a future
    session) can see who's working on it. Suggested format: '<repo|cwd-context>
    <agent-name>' e.g. 'myrepo kit-lite' or 'briefcase kit'. Keep it
    lean - this is a signal, not a long log message.
    """
    try:
        if not claimed_by or not claimed_by.strip():
            return {"status": "error", "message": "claimed_by is required"}

        conn = get_db_connection()
        item = get_triage_item(conn, item_id)
        if not item:
            conn.close()
            return {"status": "error", "message": f"Triage item #{item_id} not found"}

        ok = db_claim_triage_item(conn, item_id, claimed_by.strip())
        # Re-read so we can return the canonical claim state
        item_after = get_triage_item(conn, item_id) if ok else item
        conn.close()

        if not ok:
            return {
                "status": "error",
                "message": (
                    f"Couldn't claim #{item_id}: status is "
                    f"'{item.get('status')}' (already claimed by "
                    f"'{item.get('claimed_by') or 'unknown'}' at "
                    f"'{item.get('claimed_at') or 'unknown'}')."
                ),
                "failed_reason": "already_claimed",
                "current_claimed_by": item.get('claimed_by'),
                "current_claimed_at": item.get('claimed_at'),
            }

        return {
            "status": "success",
            "triage_item_id": item_id,
            "claimed_by": item_after.get('claimed_by'),
            "claimed_at": item_after.get('claimed_at'),
            "message": f"Claimed #{item_id} as '{claimed_by.strip()}'."
        }
    except Exception as e:
        logger.error(f"claim_triage_item error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "claim_triage_item"
TOOL_DESCRIPTION = (
    "Atomically claim a pending triage queue item before working on it. "
    "Flips the item from 'pending' to 'in_progress' and stamps "
    "claimed_at + claimed_by so other agents/sessions see it's being "
    "handled. Atomicity is enforced by SQL: if another agent claimed "
    "first, this fails cleanly. ALWAYS call this before processing a "
    "queue item when there's any chance another session could be in "
    "the same queue (e.g. when running kit-lite from one cwd while a "
    "Kit session is also active). claimed_by is a short signal label "
    "(e.g. 'tw-repo kit-lite' or 'briefcase kit')."
)
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "item_id": {
            "type": "integer",
            "description": "Triage queue item ID."
        },
        "claimed_by": {
            "type": "string",
            "description": "Short label identifying the claiming agent. Suggested format: '<cwd-context> <agent-name>' e.g. 'tw-repo kit-lite' or 'briefcase kit'. Lean signal, not a log message."
        }
    },
    "required": ["item_id", "claimed_by"]
}

__all__ = ['claim_triage_item', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
