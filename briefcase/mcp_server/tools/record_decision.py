"""MCP Tool: record_decision - Log a decision under a specific initiative."""

import logging
from typing import Optional

from briefcase.mcp_server.database import (
    get_db_connection, create_decision, get_initiative_by_slug
)

logger = logging.getLogger(__name__)


async def record_decision(
    decision: str,
    initiative_slug: Optional[str] = None,
    initiative_id: Optional[int] = None,
    rationale: Optional[str] = None,
    decided_at: Optional[str] = None,
    source_url: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """Record a decision in the per-initiative decision log.

    Pass either `initiative_slug` (preferred, easier to read) or `initiative_id`.
    `decision` is the one-line statement of what was decided. `rationale` is the
    optional paragraph-level "why." `decided_at` is an ISO date — defaults to
    today (UTC) if not provided.

    Decisions live in the decision_log table with status='pending'. A
    Thriveworks-repo dev session can later call `get_decision_log` to bulk-pull
    them and update its in-repo decisions.md, then `consume_decisions` to
    mark them as filed.
    """
    try:
        if not decision or not decision.strip():
            return {"status": "error", "message": "decision is required"}
        if not initiative_slug and not initiative_id:
            return {
                "status": "error",
                "message": "must provide either initiative_slug or initiative_id"
            }

        conn = get_db_connection()
        if initiative_id is None:
            init = get_initiative_by_slug(conn, initiative_slug)
            if not init:
                conn.close()
                return {
                    "status": "error",
                    "message": f"Initiative '{initiative_slug}' not found"
                }
            initiative_id = init['id']

        decision_id = create_decision(
            conn,
            initiative_id=initiative_id,
            decision=decision.strip(),
            rationale=(rationale or '').strip() or None,
            decided_at=decided_at,
            source_url=source_url,
            metadata=metadata,
        )
        conn.close()

        return {
            "status": "success",
            "decision_id": decision_id,
            "initiative_id": initiative_id,
            "initiative_slug": initiative_slug,
            "decision": decision.strip(),
            "decided_at": decided_at or "today (UTC)",
            "message": f"Recorded decision #{decision_id}"
        }
    except Exception as e:
        logger.error(f"record_decision error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "record_decision"
TOOL_DESCRIPTION = (
    "Record a decision under a specific initiative. The decision lives in "
    "the decision_log table with status='pending' until a downstream session "
    "(e.g. a Thriveworks-repo dev session updating decisions.md) consumes it. "
    "Kit calls this during triage when a queue item has flags.is_decision=true. "
    "Pass `decision` (the one-liner), `initiative_slug` (or _id), and "
    "optionally `rationale`, `decided_at` (YYYY-MM-DD), `source_url`, "
    "`metadata`."
)
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {
            "type": "string",
            "description": "One-line statement of what was decided."
        },
        "initiative_slug": {
            "type": "string",
            "description": "Slug of the initiative this decision belongs to. Use this OR initiative_id."
        },
        "initiative_id": {
            "type": "integer",
            "description": "ID of the initiative. Use this OR initiative_slug."
        },
        "rationale": {
            "type": "string",
            "description": "Optional paragraph-level explanation of why."
        },
        "decided_at": {
            "type": "string",
            "description": "ISO date 'YYYY-MM-DD' when the decision was made. Defaults to today (UTC) if omitted. Pull from chat timestamps when available."
        },
        "source_url": {
            "type": "string",
            "description": "Optional permalink to the conversation/doc where the decision was made (e.g. Google Chat message link)."
        },
        "metadata": {
            "type": "object",
            "description": "Free-form metadata (sender, channel, attendees, etc.). Stored as JSON."
        }
    },
    "required": ["decision"]
}

__all__ = ['record_decision', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
