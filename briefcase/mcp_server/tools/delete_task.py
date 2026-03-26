"""MCP Tool: delete_task - Permanently remove an inbox item."""

import logging
from briefcase.mcp_server.database import get_db_connection, delete_inbox_item

logger = logging.getLogger(__name__)


async def delete_task(task_id: int) -> dict:
    """Permanently delete an inbox item."""
    try:
        conn = get_db_connection()
        found = delete_inbox_item(conn, task_id)
        conn.close()

        if not found:
            return {"status": "error", "message": f"Task {task_id} not found"}

        return {"status": "success", "message": f"Task {task_id} deleted"}
    except Exception as e:
        logger.error(f"delete_task error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "delete_task"
TOOL_DESCRIPTION = "Permanently remove an inbox item."
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "task_id": {"type": "integer", "description": "ID of the inbox item to delete"}
    },
    "required": ["task_id"]
}

__all__ = ['delete_task', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
