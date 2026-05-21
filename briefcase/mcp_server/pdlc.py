"""Read-only loader for the PDLC repo (~/Programming/pdlc/).

PDLC is the product team's source of truth for business context. We never write
to it from BriefCase — slash commands in the PDLC repo handle that. These
helpers just parse YAML and surface project/initiative data to Kit.
"""

import json
import logging
from pathlib import Path
from typing import Optional
import yaml

from briefcase.mcp_server.config import load_settings

logger = logging.getLogger(__name__)


def get_pdlc_root() -> Path:
    """Resolve the configured PDLC repo path."""
    settings = load_settings()
    return Path(settings['pdlc_repo']).expanduser()


def _load_yaml(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        logger.warning("Failed to parse %s: %s", path, e)
        return None


def load_project(project_dir: Path) -> Optional[dict]:
    """Load a single context.yaml. Returns the parsed dict or None."""
    return _load_yaml(project_dir / "context.yaml")


def iter_projects() -> list[dict]:
    """Return [{dir_name, path, context}] for every project with a context.yaml."""
    root = get_pdlc_root()
    projects_dir = root / "projects"
    if not projects_dir.exists():
        return []

    out = []
    for child in sorted(projects_dir.iterdir()):
        if not child.is_dir():
            continue
        ctx = load_project(child)
        if ctx is None:
            continue
        out.append({
            "dir_name": child.name,
            "path": str(child),
            "context": ctx,
        })
    return out


def load_initiatives() -> list[dict]:
    """Return the parsed initiatives list from initiatives.yaml (or [])."""
    data = _load_yaml(get_pdlc_root() / "initiatives.yaml") or {}
    items = data.get("initiatives") or []
    return [i for i in items if isinstance(i, dict)]


def parse_initiative_tags(raw) -> list[str]:
    """Initiatives store tags as JSON in SQLite. Parse defensively."""
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def briefcase_links_for(project_id: str, initiatives: list[dict]) -> list[dict]:
    """Find Kit initiatives tagged `pdlc-project:<project_id>`."""
    needle = f"pdlc-project:{project_id}"
    matches = []
    for row in initiatives:
        tags = parse_initiative_tags(row.get("tags"))
        if needle in tags:
            matches.append({
                "slug": row.get("slug"),
                "name": row.get("name"),
                "status": row.get("status"),
            })
    return matches


def briefcase_links_for_initiative(initiative_id: str, initiatives: list[dict]) -> list[dict]:
    """Find Kit initiatives tagged `pdlc-initiative:<initiative_id>`."""
    needle = f"pdlc-initiative:{initiative_id}"
    matches = []
    for row in initiatives:
        tags = parse_initiative_tags(row.get("tags"))
        if needle in tags:
            matches.append({
                "slug": row.get("slug"),
                "name": row.get("name"),
                "status": row.get("status"),
            })
    return matches


def project_summary(entry: dict) -> dict:
    """Project entry → flat summary dict (no nested context)."""
    ctx = entry["context"]
    project = ctx.get("project") or {}
    return {
        "id": project.get("id"),
        "name": project.get("name"),
        "team": project.get("team"),
        "phase": project.get("phase"),
        "track": project.get("track"),
        "process_owner": project.get("process_owner"),
        "product_lead": project.get("product_lead"),
        "tech_lead": project.get("tech_lead"),
        "stakeholders": project.get("stakeholders") or [],
        "initiative": project.get("initiative"),
        "jira": project.get("jira"),
        "dir_name": entry["dir_name"],
        "path": entry["path"],
    }


__all__ = [
    "get_pdlc_root",
    "iter_projects",
    "load_project",
    "load_initiatives",
    "parse_initiative_tags",
    "briefcase_links_for",
    "briefcase_links_for_initiative",
    "project_summary",
]
