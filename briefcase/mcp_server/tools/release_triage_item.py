"""MCP Tool: release_triage_item - Release a claimed item back to pending."""

import logging

from briefcase.mcp_server.database import (
    get_db_connection, release_triage_item as db_release_triage_item,
    get_triage_item,
)

logger = logging.getLogger(__name__)


async def release_triage_item(item_id: int) -> dict:
    """Flip an in_progress triage queue item back to 'pending', clearing
    claimed_at and claimed_by.

    Use when:
      - An agent realized it shouldn't handle this item after all
      - A claim is stale (claimed_at >1hr old, claimer probably gone)
      - Switching agents mid-flow

    Does NOT delete the item; it just goes back to the pending pool.
    """
    try:
        conn = get_db_connection()
        item = get_triage_item(conn, item_id)
        if not item:
            conn.close()
            return {"status": "error", "message": f"Triage item #{item_id} not found"}

        if item.get('status') != 'in_progress':
            conn.close()
            return {
                "status": "error",
                "message": (
                    f"Can't release #{item_id}: status is "
                    f"'{item.get('status')}' (only in_progress items "
                    f"can be released)."
                )
            }

        prev_claimed_by = item.get('claimed_by')
        prev_claimed_at = item.get('claimed_at')
        ok = db_release_triage_item(conn, item_id)
        conn.close()

        if not ok:
            return {
                "status": "error",
                "message": f"Failed to release #{item_id} (race or status changed)."
            }

        return {
            "status": "success",
            "triage_item_id": item_id,
            "previous_claimed_by": prev_claimed_by,
            "previous_claimed_at": prev_claimed_at,
            "message": (
                f"Released #{item_id} (was claimed by "
                f"'{prev_claimed_by or 'unknown'}'). Now back to pending."
            )
        }
    except Exception as e:
        logger.error(f"release_triage_item error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "release_triage_item"
TOOL_DESCRIPTION = (
    "Flip an in_progress triage queue item back to 'pending', clearing "
    "the claim. Use when an agent decides not to handle the item after "
    "claiming, when a claim is stale, or when explicitly handing off to "
    "another session. Does NOT delete the item."
)
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "item_id": {
            "type": "integer",
            "description": "Triage queue item ID currently in 'in_progress' status."
        }
    },
    "required": ["item_id"]
}

__all__ = ['release_triage_item', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
