"""MCP Tool: add_external_ref - Attach a Jira/Confluence/etc. reference to
an initiative or inbox item."""

import logging
from typing import Optional

from briefcase.mcp_server.database import (
    get_db_connection, add_external_ref as db_add_ref
)
from briefcase.mcp_server.refs import derive_ref_url, KNOWN_REF_TYPES

logger = logging.getLogger(__name__)


async def add_external_ref(
    entity_type: str,
    entity_id: int,
    ref_type: str,
    ref_key: str,
    ref_url: Optional[str] = None,
    label: Optional[str] = None,
) -> dict:
    """Attach an external reference (Jira ticket, Confluence page, Figma file,
    GitHub PR, etc.) to an initiative or inbox item.

    ref_url is optional. For known ref_types (jira_epic, jira_ticket) the URL
    will be derived from the integrations config in settings.yaml if not given.
    """
    try:
        conn = get_db_connection()
        resolved_url = derive_ref_url(ref_type, ref_key, explicit_url=ref_url)
        ref_id = db_add_ref(
            conn, entity_type=entity_type, entity_id=entity_id,
            ref_type=ref_type, ref_key=ref_key, ref_url=resolved_url,
            label=label
        )
        conn.close()

        return {
            "status": "success",
            "ref_id": ref_id,
            "ref_type": ref_type,
            "ref_key": ref_key,
            "ref_url": resolved_url,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "label": label,
        }
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.error(f"add_external_ref error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "add_external_ref"
TOOL_DESCRIPTION = (
    "Attach an external reference (Jira ticket, Confluence page, Figma file, "
    "GitHub PR, etc.) to an initiative or inbox item. ref_url is auto-derived "
    "for known ref_types (jira_epic, jira_ticket) when not provided. Use to "
    "track the remote systems an initiative lives in."
)
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "entity_type": {
            "type": "string",
            "enum": ["initiative", "inbox"],
            "description": "Which kind of local entity the ref attaches to."
        },
        "entity_id": {
            "type": "integer",
            "description": "ID of the initiative or inbox item."
        },
        "ref_type": {
            "type": "string",
            "enum": sorted(list(KNOWN_REF_TYPES)),
            "description": "Kind of external reference. Jira types auto-derive URL."
        },
        "ref_key": {
            "type": "string",
            "description": "Short key or URL. e.g. 'THRIV-13413', or a full URL for generic refs."
        },
        "ref_url": {
            "type": "string",
            "description": "Optional explicit URL. Overrides automatic derivation."
        },
        "label": {
            "type": "string",
            "description": "Optional human-readable label (e.g. the ticket title)."
        },
    },
    "required": ["entity_type", "entity_id", "ref_type", "ref_key"],
}

__all__ = ['add_external_ref', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
