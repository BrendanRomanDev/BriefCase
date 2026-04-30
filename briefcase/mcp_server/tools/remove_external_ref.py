"""MCP Tool: remove_external_ref - Detach an external reference by ID."""

import logging

from briefcase.mcp_server.database import (
    get_db_connection, remove_external_ref as db_remove_ref
)

logger = logging.getLogger(__name__)


async def remove_external_ref(ref_id: int) -> dict:
    """Delete an external ref by its ID."""
    try:
        conn = get_db_connection()
        found = db_remove_ref(conn, ref_id)
        conn.close()
        if not found:
            return {"status": "error", "message": f"Ref #{ref_id} not found"}
        return {"status": "success", "message": f"Removed ref #{ref_id}"}
    except Exception as e:
        logger.error(f"remove_external_ref error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "remove_external_ref"
TOOL_DESCRIPTION = (
    "Delete an external reference by its ID (find the ID via list_external_refs)."
)
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "ref_id": {"type": "integer", "description": "External ref ID to remove."},
    },
    "required": ["ref_id"],
}

__all__ = ['remove_external_ref', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
