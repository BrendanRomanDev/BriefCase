"""MCP Tool: search_notes - Search the Obsidian vault by keyword."""

import logging
from typing import Optional
from briefcase.mcp_server.obsidian import search_vault, get_initiative_folder

logger = logging.getLogger(__name__)


async def search_notes(
    query: str,
    initiative_slug: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    include_legacy: bool = False
) -> dict:
    """Search the Obsidian vault by keyword, optionally scoped to initiative/date."""
    try:
        # Determine search scope
        search_dir = None
        if initiative_slug:
            search_dir = get_initiative_folder(initiative_slug)

        date_range = None
        if date_start and date_end:
            date_range = (date_start, date_end)

        results = search_vault(
            query=query,
            relative_dir=search_dir,
            date_range=date_range
        )

        # Optionally search legacy too
        legacy_results = []
        if include_legacy:
            legacy_dir = "legacy"
            if initiative_slug:
                # Map known slugs to legacy folder names
                slug_to_legacy = {
                    'insurance-management': 'legacy/insurance',
                }
                legacy_dir = slug_to_legacy.get(initiative_slug, f"legacy/{initiative_slug}")

            legacy_results = search_vault(
                query=query,
                relative_dir=legacy_dir,
                date_range=date_range
            )

        all_results = results + legacy_results

        return {
            "status": "success",
            "query": query,
            "scope": initiative_slug or "entire vault",
            "count": len(all_results),
            "results": all_results,
            "legacy_count": len(legacy_results) if include_legacy else 0
        }
    except Exception as e:
        logger.error(f"search_notes error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "search_notes"
TOOL_DESCRIPTION = "Search the Obsidian vault by keyword. Optionally scoped to an initiative folder and/or date range."
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Search term"},
        "initiative_slug": {"type": "string", "description": "Scope search to this initiative's folder"},
        "date_start": {"type": "string", "description": "Start of date range (YYYY-MM-DD)"},
        "date_end": {"type": "string", "description": "End of date range (YYYY-MM-DD)"},
        "include_legacy": {"type": "boolean", "description": "Also search legacy/ folder (default false)"}
    },
    "required": ["query"]
}

__all__ = ['search_notes', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
