"""MCP Tool: list_pdlc_projects - List PDLC projects with Kit linkage status."""

import logging
from typing import Optional

from briefcase.mcp_server.database import get_db_connection, get_all_initiatives
from briefcase.mcp_server.pdlc import (
    iter_projects, load_initiatives, briefcase_links_for,
    briefcase_links_for_initiative, project_summary, get_pdlc_root,
)

logger = logging.getLogger(__name__)

DEFAULT_LANE_TEAM = "client-experience"
DEFAULT_LANE_TECH_LEAD = "Brendan Roman"


def _project_matches_lane(project: dict, my_lane: bool,
                          team: Optional[str], tech_lead: Optional[str],
                          phase: Optional[str]) -> bool:
    if team and project.get("team") != team:
        return False
    if tech_lead and project.get("tech_lead") != tech_lead:
        return False
    if phase and project.get("phase") != phase:
        return False

    if my_lane and not (team or tech_lead):
        in_lane = (
            project.get("team") == DEFAULT_LANE_TEAM
            or project.get("tech_lead") == DEFAULT_LANE_TECH_LEAD
        )
        if not in_lane:
            return False

    return True


async def list_pdlc_projects(
    my_lane: bool = True,
    team: Optional[str] = None,
    tech_lead: Optional[str] = None,
    phase: Optional[str] = None,
    include_initiatives: bool = False,
) -> dict:
    """List PDLC projects (and optionally roadmap initiatives) with Kit linkage."""
    try:
        pdlc_root = get_pdlc_root()
        if not pdlc_root.exists():
            return {
                "status": "error",
                "message": f"PDLC repo not found at {pdlc_root}. "
                           "Set `pdlc_repo` in settings.yaml or clone the repo there."
            }

        conn = get_db_connection()
        kit_initiatives = get_all_initiatives(conn)
        conn.close()

        projects_out = []
        unlinked_count = 0

        for entry in iter_projects():
            summary = project_summary(entry)
            if not _project_matches_lane(summary, my_lane, team, tech_lead, phase):
                continue

            links = briefcase_links_for(summary["id"], kit_initiatives) \
                if summary["id"] else []
            summary["briefcase_links"] = links
            if not links:
                unlinked_count += 1
            projects_out.append(summary)

        result = {
            "status": "success",
            "projects": projects_out,
            "count": len(projects_out),
            "unlinked_count": unlinked_count,
            "filters": {
                "my_lane": my_lane,
                "team": team,
                "tech_lead": tech_lead,
                "phase": phase,
            },
        }

        if include_initiatives:
            initiatives_out = []
            for init in load_initiatives():
                if team and init.get("team") != team:
                    continue
                if my_lane and not team and init.get("team") != DEFAULT_LANE_TEAM:
                    continue
                init_id = init.get("id")
                links = briefcase_links_for_initiative(init_id, kit_initiatives) \
                    if init_id else []
                initiatives_out.append({
                    "id": init_id,
                    "name": init.get("name"),
                    "team": init.get("team"),
                    "owner": init.get("owner"),
                    "quarter": init.get("quarter"),
                    "description": init.get("description"),
                    "briefcase_links": links,
                })
            result["initiatives"] = initiatives_out
            result["initiatives_count"] = len(initiatives_out)

        return result

    except Exception as e:
        logger.error(f"list_pdlc_projects error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "list_pdlc_projects"
TOOL_DESCRIPTION = (
    "List PDLC projects with Kit linkage status. Defaults to Brendan's lane "
    "(team=client-experience OR tech_lead=Brendan Roman). Each project includes "
    "briefcase_links — Kit initiatives tagged `pdlc-project:<id>`. Empty briefcase_links "
    "means the project hasn't been linked to Kit yet."
)
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "my_lane": {
            "type": "boolean", "default": True,
            "description": "Filter to Brendan's lane (client-experience team OR Brendan as tech lead). Ignored if `team` or `tech_lead` is given explicitly."
        },
        "team": {"type": "string", "description": "Filter by team slug (e.g., client-experience, finding-care)"},
        "tech_lead": {"type": "string", "description": "Filter by tech_lead name"},
        "phase": {"type": "string", "description": "Filter by PDLC phase (intake, planning, solutioning, pilot, launch, post_launch_monitoring)"},
        "include_initiatives": {
            "type": "boolean", "default": False,
            "description": "Also include roadmap-level initiatives (ce-i001, ce-i002, ...) from initiatives.yaml"
        },
    }
}

__all__ = ['list_pdlc_projects', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
