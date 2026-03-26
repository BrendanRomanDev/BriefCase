"""MCP Tool: draft_status_update - Synthesize initiative context into a stakeholder update."""

import logging
import subprocess
from datetime import datetime, timedelta
from typing import Optional
from briefcase.mcp_server.database import (
    get_db_connection, get_initiative_by_slug, get_inbox_items,
    get_initiative_members
)
from briefcase.mcp_server.obsidian import (
    list_recent_files, read_file, get_meetings_folder, get_initiative_folder
)

logger = logging.getLogger(__name__)


def _run_command(cmd: list[str], cwd: str = None) -> Optional[str]:
    """Run a CLI command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15, cwd=cwd
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


async def draft_status_update(
    initiative_slug: str,
    period: Optional[str] = None,
    period_days: int = 7
) -> dict:
    """Pull initiative context and return structured data for the agent to draft
    a stakeholder update. The agent formats the final prose — this tool gathers
    the raw material."""
    try:
        conn = get_db_connection()
        initiative = get_initiative_by_slug(conn, initiative_slug)

        if not initiative:
            conn.close()
            return {"status": "error", "message": f"Initiative '{initiative_slug}' not found"}

        if not period:
            end = datetime.now()
            start = end - timedelta(days=period_days)
            period = f"{start.strftime('%b %-d')} – {end.strftime('%b %-d, %Y')}"

        # DB: team
        members = get_initiative_members(conn, initiative['id'])

        # DB: open items
        open_items = get_inbox_items(conn, initiative_slug=initiative_slug)

        # DB: recently completed
        completed = conn.execute(
            """SELECT id, title, completed_at FROM inbox
               WHERE initiative_id = ? AND completed_at IS NOT NULL
               AND completed_at >= datetime('now', ?)
               ORDER BY completed_at DESC""",
            (initiative['id'], f"-{period_days} days")
        ).fetchall()
        completed = [dict(row) for row in completed]

        conn.close()

        # Obsidian: README + recent meeting notes
        readme_path = f"{get_initiative_folder(initiative_slug)}/README.md"
        readme = read_file(readme_path)

        meetings_folder = get_meetings_folder(initiative_slug)
        recent_notes = list_recent_files(meetings_folder, days=period_days)

        note_summaries = []
        for note_file in recent_notes[:5]:
            content = read_file(note_file['path'])
            if content:
                note_summaries.append({
                    "filename": note_file['name'],
                    "date": note_file.get('date'),
                    "content": content[:2000]
                })

        # GitHub: repo activity
        repo_activity = {}
        repo_path = initiative.get('repo_path')
        if repo_path:
            merged_prs = _run_command(
                ['gh', 'pr', 'list', '--state', 'merged', '--limit', '10'],
                cwd=repo_path
            )
            if merged_prs:
                repo_activity['merged_prs'] = merged_prs

            open_prs = _run_command(
                ['gh', 'pr', 'list', '--state', 'open', '--limit', '10'],
                cwd=repo_path
            )
            if open_prs:
                repo_activity['open_prs'] = open_prs

            recent_commits = _run_command(
                ['git', 'log', '--oneline', f'--since={period_days} days ago'],
                cwd=repo_path
            )
            if recent_commits:
                lines = recent_commits.split('\n')
                repo_activity['recent_commits'] = '\n'.join(lines[:20])
                repo_activity['commit_count'] = len(lines)

        return {
            "status": "success",
            "initiative": {
                "name": initiative['name'],
                "slug": initiative['slug'],
                "status": initiative['status'],
                "deadline": initiative.get('deadline'),
                "description": initiative.get('description'),
            },
            "period": period,
            "team": members,
            "completed_items": completed,
            "open_items": open_items,
            "readme_context": readme,
            "meeting_notes": note_summaries,
            "repo_activity": repo_activity,
            "formatting_instructions": (
                "Draft a professional stakeholder update from this data. "
                "Lead with outcomes, not tasks. Connect technical work to business value. "
                "Keep it under 300 words. Sections: Progress, Current Status, "
                "Blockers/Risks, Upcoming. No emojis. Present the draft for Brendan "
                "to review before sending."
            )
        }

    except Exception as e:
        logger.error(f"draft_status_update error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "draft_status_update"
TOOL_DESCRIPTION = "Gather initiative context from DB, Obsidian, and gh CLI for the agent to draft a stakeholder update."
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "initiative_slug": {"type": "string", "description": "Initiative slug"},
        "period": {"type": "string", "description": "Period label (e.g., 'this week', 'March 20-26'). Auto-generated if omitted."},
        "period_days": {"type": "integer", "default": 7,
                       "description": "Number of days to look back (default 7)"}
    },
    "required": ["initiative_slug"]
}

__all__ = ['draft_status_update', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
