"""MCP Tool: consume_decisions - Mark decisions as consumed after they've been
filed somewhere downstream (e.g. into a repo's decisions.md)."""

import logging
from typing import Optional

from briefcase.mcp_server.database import (
    get_db_connection, consume_decisions as db_consume_decisions
)

logger = logging.getLogger(__name__)


async def consume_decisions(
    initiative_slug: Optional[str] = None,
    initiative_id: Optional[int] = None,
    decision_ids: Optional[list] = None,
) -> dict:
    """Flip decisions from 'pending' to 'consumed' after they've been filed
    into a downstream artifact (e.g. a Thriveworks-repo decisions.md file).

    Filter modes (at least one required to prevent mass-mutation):
      - decision_ids: mark exactly those rows
      - initiative_slug or initiative_id: mark all pending decisions for
        that initiative

    Decisions are NOT deleted - they keep history with consumed_at set.
    Use status='consumed' or 'all' on get_decision_log to see them.
    """
    try:
        if not decision_ids and not initiative_slug and not initiative_id:
            return {
                "status": "error",
                "message": "Must specify decision_ids, initiative_slug, or initiative_id"
            }

        conn = get_db_connection()
        count = db_consume_decisions(
            conn,
            initiative_id=initiative_id,
            initiative_slug=initiative_slug,
            ids=decision_ids,
        )
        conn.close()

        return {
            "status": "success",
            "consumed": count,
            "message": f"Marked {count} decision(s) consumed."
        }
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.error(f"consume_decisions error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "consume_decisions"
TOOL_DESCRIPTION = (
    "Mark decisions as 'consumed' after they've been filed into a downstream "
    "artifact (e.g. a Thriveworks-repo decisions.md). Decisions are NOT "
    "deleted - keep history with consumed_at timestamp. Pass either "
    "`decision_ids` (specific rows) or `initiative_slug`/`initiative_id` "
    "(all pending for that initiative)."
)
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "initiative_slug": {
            "type": "string",
            "description": "Mark all pending decisions for this initiative as consumed."
        },
        "initiative_id": {
            "type": "integer",
            "description": "Mark all pending decisions for this initiative id as consumed."
        },
        "decision_ids": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Mark exactly these decision_log row ids as consumed."
        }
    }
}

__all__ = ['consume_decisions', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
