"""MCP Tool: resolve_pdlc_project - Fuzzy match a name fragment to a PDLC project id."""

import logging
import re
from difflib import SequenceMatcher

from briefcase.mcp_server.pdlc import iter_projects, project_summary, get_pdlc_root

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 1}


def _score(query: str, project: dict) -> float:
    """Combined score: token overlap + fuzzy match against name and dir_name."""
    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.0

    haystack = " ".join(filter(None, [
        project.get("id"),
        project.get("name"),
        project.get("dir_name"),
    ])).lower()
    haystack_tokens = _tokenize(haystack)

    overlap = len(query_tokens & haystack_tokens) / max(len(query_tokens), 1)
    fuzzy = SequenceMatcher(None, query.lower(), haystack).ratio()

    # Exact id match always wins.
    if project.get("id") and project["id"].lower() == query.lower().strip():
        return 1.0

    return 0.6 * overlap + 0.4 * fuzzy


async def resolve_pdlc_project(query: str, limit: int = 5) -> dict:
    """Return ranked PDLC project candidates for a topic/name fragment."""
    try:
        pdlc_root = get_pdlc_root()
        if not pdlc_root.exists():
            return {
                "status": "error",
                "message": f"PDLC repo not found at {pdlc_root}."
            }

        if not query or not query.strip():
            return {"status": "error", "message": "Query is empty."}

        candidates = []
        for entry in iter_projects():
            summary = project_summary(entry)
            score = _score(query, summary)
            if score > 0:
                candidates.append({
                    "id": summary["id"],
                    "name": summary["name"],
                    "team": summary["team"],
                    "phase": summary["phase"],
                    "tech_lead": summary["tech_lead"],
                    "dir_name": summary["dir_name"],
                    "score": round(score, 3),
                })

        candidates.sort(key=lambda c: c["score"], reverse=True)
        top = candidates[:limit]

        return {
            "status": "success",
            "query": query,
            "matches": top,
            "best_match": top[0] if top else None,
            "count": len(top),
        }

    except Exception as e:
        logger.error(f"resolve_pdlc_project error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "resolve_pdlc_project"
TOOL_DESCRIPTION = (
    "Fuzzy-match a name fragment or topic to PDLC project ids. Use when the user "
    "refers to a project by topic ('the medicare thing' → ce-004). Returns ranked "
    "candidates with scores."
)
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Name fragment, topic, or partial id to match"},
        "limit": {"type": "integer", "default": 5, "description": "Max candidates to return"},
    },
    "required": ["query"]
}

__all__ = ['resolve_pdlc_project', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
