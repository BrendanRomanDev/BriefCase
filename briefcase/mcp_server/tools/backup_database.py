"""MCP Tool: backup_database - Create timestamped database backup."""

import logging
from typing import Optional
from briefcase.mcp_server.database import backup_database as do_backup

logger = logging.getLogger(__name__)


async def backup_database(note: Optional[str] = None) -> dict:
    """Create timestamped backup of the database (SQL copy + JSON export)."""
    try:
        backup_path = do_backup(note=note)
        json_path = backup_path.replace('.db', '.json')

        return {
            "status": "success",
            "message": "Backup created",
            "db_backup": backup_path,
            "json_backup": json_path
        }
    except Exception as e:
        logger.error(f"backup_database error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "backup_database"
TOOL_DESCRIPTION = "Create a timestamped database backup (SQL copy + JSON export)."
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "note": {"type": "string", "description": "Optional note to include in backup filename"}
    }
}

__all__ = ['backup_database', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
