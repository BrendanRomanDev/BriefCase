"""MCP Tool: complete_task - Mark an inbox item as completed."""

import logging
from briefcase.mcp_server.database import get_db_connection, complete_inbox_item

logger = logging.getLogger(__name__)


async def complete_task(task_id: int) -> dict:
    """Mark an inbox item as completed."""
    try:
        conn = get_db_connection()
        found = complete_inbox_item(conn, task_id)
        conn.close()

        if not found:
            return {"status": "error", "message": f"Task {task_id} not found"}

        return {"status": "success", "message": f"Task {task_id} completed"}
    except Exception as e:
        logger.error(f"complete_task error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "complete_task"
TOOL_DESCRIPTION = "Mark an inbox item as completed."
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "task_id": {"type": "integer", "description": "ID of the inbox item to complete"}
    },
    "required": ["task_id"]
}

__all__ = ['complete_task', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
