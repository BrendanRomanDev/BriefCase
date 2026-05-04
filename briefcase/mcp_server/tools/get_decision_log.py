"""MCP Tool: get_decision_log - Pull pending (or all) decisions for an initiative."""

import logging
from typing import Optional

from briefcase.mcp_server.database import get_db_connection, get_decisions

logger = logging.getLogger(__name__)


async def get_decision_log(
    initiative_slug: Optional[str] = None,
    initiative_id: Optional[int] = None,
    status: Optional[str] = "pending",
) -> dict:
    """Query the decision log. Filter by initiative and/or status.

    Default status='pending' returns decisions that haven't been consumed
    yet — typically what a Thriveworks-repo dev session wants when bulk-
    updating an in-repo decisions.md file.

    Pass status='all' (or None / empty) to include consumed decisions too.
    """
    try:
        conn = get_db_connection()
        effective_status = None if (status in (None, "", "all")) else status
        rows = get_decisions(
            conn,
            initiative_id=initiative_id,
            initiative_slug=initiative_slug,
            status=effective_status,
        )
        conn.close()

        return {
            "status": "success",
            "count": len(rows),
            "decisions": rows,
            "filters": {
                "initiative_slug": initiative_slug,
                "initiative_id": initiative_id,
                "status": status,
            }
        }
    except Exception as e:
        logger.error(f"get_decision_log error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "get_decision_log"
TOOL_DESCRIPTION = (
    "Query the decision log. Default status='pending' returns decisions "
    "that haven't been consumed yet - typically what a Thriveworks-repo "
    "dev session wants when bulk-updating an in-repo decisions.md file. "
    "Use status='consumed' or 'all' to see history. Each row carries "
    "decision, rationale, decided_at, source_url, and metadata."
)
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "initiative_slug": {
            "type": "string",
            "description": "Filter to one initiative by slug."
        },
        "initiative_id": {
            "type": "integer",
            "description": "Filter to one initiative by id."
        },
        "status": {
            "type": "string",
            "enum": ["pending", "consumed", "all"],
            "description": "Filter by status. Default 'pending'. Pass 'all' to include consumed."
        }
    }
}

__all__ = ['get_decision_log', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
