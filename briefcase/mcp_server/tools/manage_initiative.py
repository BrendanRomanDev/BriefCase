"""MCP Tool: manage_initiative - CRUD for initiatives."""

import logging
from typing import Optional
from briefcase.mcp_server.database import (
    get_db_connection, create_initiative, get_initiative_by_slug,
    get_all_initiatives, update_initiative
)
from briefcase.mcp_server.obsidian import scaffold_initiative_folder

logger = logging.getLogger(__name__)


async def manage_initiative(
    action: str,
    slug: Optional[str] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    deadline: Optional[str] = None,
    tags: Optional[list] = None,
    repo_path: Optional[str] = None,
    status: Optional[str] = None,
    create_obsidian_folder: bool = True,
    tags_mode: str = 'append',
    source: Optional[str] = None,
    source_url: Optional[str] = None,
    source_metadata: Optional[dict] = None
) -> dict:
    """CRUD for initiatives."""
    try:
        conn = get_db_connection()

        if action == "create":
            if not name or not slug:
                return {"status": "error", "message": "name and slug are required for create"}

            existing = get_initiative_by_slug(conn, slug)
            if existing:
                conn.close()
                return {"status": "error", "message": f"Initiative '{slug}' already exists"}

            initiative_id = create_initiative(
                conn, name=name, slug=slug, description=description,
                deadline=deadline, tags=tags, repo_path=repo_path,
                source=source, source_url=source_url,
                source_metadata=source_metadata
            )

            result = {"status": "success", "message": f"Created initiative: {name}", "id": initiative_id}

            if create_obsidian_folder:
                project_dir = scaffold_initiative_folder(slug, name, description)
                result["obsidian_folder"] = str(project_dir)

            conn.close()
            return result

        elif action == "update":
            if not slug:
                conn.close()
                return {"status": "error", "message": "slug is required for update"}

            updates = {}
            if name is not None:
                updates['name'] = name
            if description is not None:
                updates['description'] = description
            if deadline is not None:
                updates['deadline'] = deadline
            if tags is not None:
                updates['tags'] = tags
            if repo_path is not None:
                updates['repo_path'] = repo_path
            if status is not None:
                updates['status'] = status

            if tags_mode not in ('append', 'replace', 'remove'):
                conn.close()
                return {"status": "error",
                        "message": f"tags_mode must be append, replace, or remove (got '{tags_mode}')"}

            found = update_initiative(conn, slug, tags_mode=tags_mode, **updates)
            conn.close()

            if not found:
                return {"status": "error", "message": f"Initiative '{slug}' not found"}
            return {"status": "success", "message": f"Updated initiative: {slug}"}

        elif action == "get":
            if not slug:
                conn.close()
                return {"status": "error", "message": "slug is required for get"}

            initiative = get_initiative_by_slug(conn, slug)
            conn.close()

            if not initiative:
                return {"status": "error", "message": f"Initiative '{slug}' not found"}
            return {"status": "success", "initiative": initiative}

        elif action == "list":
            initiatives = get_all_initiatives(conn, status=status)
            conn.close()
            return {"status": "success", "count": len(initiatives), "initiatives": initiatives}

        elif action == "archive":
            if not slug:
                conn.close()
                return {"status": "error", "message": "slug is required for archive"}

            found = update_initiative(conn, slug, status='completed')
            conn.close()

            if not found:
                return {"status": "error", "message": f"Initiative '{slug}' not found"}
            return {"status": "success", "message": f"Archived initiative: {slug}"}

        else:
            conn.close()
            return {"status": "error", "message": f"Unknown action: {action}. Use create, update, get, list, or archive."}

    except Exception as e:
        logger.error(f"manage_initiative error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "manage_initiative"
TOOL_DESCRIPTION = "CRUD for initiatives/projects. Actions: create, update, get, list, archive."
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["create", "update", "get", "list", "archive"],
                   "description": "CRUD action to perform"},
        "slug": {"type": "string", "description": "Initiative slug (required for create/update/get/archive)"},
        "name": {"type": "string", "description": "Initiative name (required for create)"},
        "description": {"type": "string", "description": "Brief description"},
        "deadline": {"type": "string", "description": "Deadline date (YYYY-MM-DD)"},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags for categorization"},
        "repo_path": {"type": "string", "description": "Path to git repo"},
        "status": {"type": "string", "description": "Status filter (for list) or new status (for update)"},
        "create_obsidian_folder": {"type": "boolean", "description": "Create Obsidian folder structure on create (default true)"},
        "tags_mode": {"type": "string", "enum": ["append", "replace", "remove"],
                      "description": "How to apply 'tags' on update. 'append' (default) merges with existing and dedupes. 'replace' overwrites. 'remove' subtracts."},
        "source": {"type": "string",
                   "description": "Where this initiative origin came from (e.g. 'google_chat', 'web_clip'). Only applies on create."},
        "source_url": {"type": "string",
                       "description": "Permalink back to the origin (e.g. the Google Chat message that prompted this initiative). Only applies on create."},
        "source_metadata": {"type": "object",
                            "description": "Free-form metadata about the source. Only applies on create."}
    },
    "required": ["action"]
}

__all__ = ['manage_initiative', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
