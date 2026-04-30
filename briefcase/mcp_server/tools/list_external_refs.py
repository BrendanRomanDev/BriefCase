"""MCP Tool: list_external_refs - Query external references."""

import logging
from typing import Optional

from briefcase.mcp_server.database import get_db_connection, get_external_refs
from briefcase.mcp_server.refs import derive_ref_url

logger = logging.getLogger(__name__)


async def list_external_refs(
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    ref_type: Optional[str] = None,
    ref_key: Optional[str] = None,
) -> dict:
    """Query external refs. All filters optional.

    Useful forms:
      - entity_type + entity_id: every ref for one initiative/inbox item
      - ref_key: reverse lookup - everything linked to a given Jira key
      - ref_type: all refs of a kind (e.g. every jira_epic tracked)

    ref_url is back-filled if missing and derivable (so older rows benefit
    from current settings).
    """
    try:
        conn = get_db_connection()
        rows = get_external_refs(
            conn,
            entity_type=entity_type,
            entity_id=entity_id,
            ref_type=ref_type,
            ref_key=ref_key,
        )
        conn.close()

        for r in rows:
            if not r.get('ref_url'):
                r['ref_url'] = derive_ref_url(r.get('ref_type'), r.get('ref_key'))

        return {
            "status": "success",
            "count": len(rows),
            "refs": rows,
            "filters": {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "ref_type": ref_type,
                "ref_key": ref_key,
            },
        }
    except Exception as e:
        logger.error(f"list_external_refs error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "list_external_refs"
TOOL_DESCRIPTION = (
    "Query external references. Filter by entity (initiative/inbox + id), "
    "ref_type (jira_epic, jira_ticket, confluence, figma, etc.), or ref_key "
    "for reverse lookup. Each result includes a canonical ref_url so you can "
    "render clickable links inline."
)
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "entity_type": {
            "type": "string",
            "enum": ["initiative", "inbox"],
            "description": "Filter to this entity kind."
        },
        "entity_id": {
            "type": "integer",
            "description": "Filter to a specific entity row."
        },
        "ref_type": {
            "type": "string",
            "description": "Filter to a specific ref_type (e.g. 'jira_epic')."
        },
        "ref_key": {
            "type": "string",
            "description": "Reverse lookup - every ref with this exact key."
        },
    },
}

__all__ = ['list_external_refs', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
