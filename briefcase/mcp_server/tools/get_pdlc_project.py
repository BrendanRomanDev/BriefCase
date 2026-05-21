"""MCP Tool: get_pdlc_project - Summary of one PDLC project + linked Kit initiatives."""

import logging
from pathlib import Path

from briefcase.mcp_server.database import get_db_connection, get_all_initiatives
from briefcase.mcp_server.pdlc import (
    iter_projects, load_project, briefcase_links_for, project_summary,
    get_pdlc_root,
)

logger = logging.getLogger(__name__)


def _find_project_dir(project_id: str) -> Path | None:
    """Locate the project directory by id prefix (e.g., 'ce-004' → ce-004-...)."""
    root = get_pdlc_root() / "projects"
    if not root.exists():
        return None
    for child in root.iterdir():
        if not child.is_dir():
            continue
        if child.name == project_id or child.name.startswith(f"{project_id}-"):
            return child
    return None


async def get_pdlc_project(project_id: str, full: bool = False) -> dict:
    """Return a project summary + linked Kit initiatives. `full=true` includes the raw context.yaml."""
    try:
        pdlc_root = get_pdlc_root()
        if not pdlc_root.exists():
            return {
                "status": "error",
                "message": f"PDLC repo not found at {pdlc_root}."
            }

        project_dir = _find_project_dir(project_id)
        if project_dir is None:
            return {
                "status": "error",
                "message": f"PDLC project '{project_id}' not found in {pdlc_root / 'projects'}."
            }

        context = load_project(project_dir)
        if context is None:
            return {
                "status": "error",
                "message": f"Could not load {project_dir / 'context.yaml'}."
            }

        entry = {
            "dir_name": project_dir.name,
            "path": str(project_dir),
            "context": context,
        }
        summary = project_summary(entry)

        conn = get_db_connection()
        kit_initiatives = get_all_initiatives(conn)
        conn.close()

        links = briefcase_links_for(summary["id"], kit_initiatives) \
            if summary["id"] else []

        project = context.get("project") or {}
        gate_status = project.get("gate_status") or {}
        artifacts = context.get("artifacts") or []
        open_questions = [
            q for q in (context.get("open_questions") or [])
            if isinstance(q, dict) and not q.get("resolved")
        ]
        decisions = context.get("decisions") or []

        result = {
            "status": "success",
            "project": summary,
            "briefcase_links": links,
            "gate_status": gate_status,
            "artifacts": [
                {
                    "id": a.get("id"),
                    "label": a.get("label"),
                    "status": a.get("status"),
                    "path": a.get("path"),
                }
                for a in artifacts if isinstance(a, dict)
            ],
            "open_questions_unresolved": open_questions,
            "decisions": decisions,
        }

        if full:
            result["raw"] = context

        return result

    except Exception as e:
        logger.error(f"get_pdlc_project error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "get_pdlc_project"
TOOL_DESCRIPTION = (
    "Get a PDLC project's summary, gate status, artifacts, open questions, and any "
    "Kit initiatives linked via `pdlc-project:<id>` tag. Pass full=true to include "
    "the raw context.yaml."
)
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "project_id": {"type": "string", "description": "PDLC project id (e.g., ce-004)"},
        "full": {
            "type": "boolean", "default": False,
            "description": "Include the raw parsed context.yaml in the response"
        },
    },
    "required": ["project_id"]
}

__all__ = ['get_pdlc_project', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
