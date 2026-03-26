"""MCP Tool: get_initiative_status - Full status report for an initiative."""

import logging
import subprocess
from typing import Optional
from briefcase.mcp_server.database import (
    get_db_connection, get_initiative_by_slug, get_inbox_items,
    get_initiative_members
)
from briefcase.mcp_server.obsidian import (
    list_recent_files, read_file, get_meetings_folder, get_initiative_folder
)

logger = logging.getLogger(__name__)


def _run_gh_command(cmd: list[str], cwd: str = None) -> Optional[str]:
    """Run a gh/git CLI command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15, cwd=cwd
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


async def get_initiative_status(
    initiative_slug: str,
    include_repo: bool = False,
    include_notes: bool = True,
    notes_days: int = 14
) -> dict:
    """Full status report for an initiative, pulling from DB, Obsidian, and optionally gh CLI."""
    try:
        conn = get_db_connection()
        initiative = get_initiative_by_slug(conn, initiative_slug)

        if not initiative:
            conn.close()
            return {"status": "error", "message": f"Initiative '{initiative_slug}' not found"}

        # DB: team members
        members = get_initiative_members(conn, initiative['id'])

        # DB: open inbox items
        open_items = get_inbox_items(conn, initiative_slug=initiative_slug)

        # DB: recently completed items
        completed = conn.execute(
            """SELECT id, title, completed_at FROM inbox
               WHERE initiative_id = ? AND completed_at IS NOT NULL
               AND completed_at >= datetime('now', '-14 days')
               ORDER BY completed_at DESC""",
            (initiative['id'],)
        ).fetchall()
        completed = [dict(row) for row in completed]

        conn.close()

        result = {
            "status": "success",
            "initiative": {
                "name": initiative['name'],
                "slug": initiative['slug'],
                "status": initiative['status'],
                "description": initiative.get('description'),
                "deadline": initiative.get('deadline'),
                "repo_path": initiative.get('repo_path'),
                "obsidian_folder": initiative.get('obsidian_folder'),
            },
            "team": members,
            "open_items": open_items,
            "recently_completed": completed,
        }

        # Obsidian: README and recent meeting notes
        if include_notes:
            readme_path = f"{get_initiative_folder(initiative_slug)}/README.md"
            readme = read_file(readme_path)
            result["readme"] = readme

            meetings_folder = get_meetings_folder(initiative_slug)
            recent_notes = list_recent_files(meetings_folder, days=notes_days)

            # Read the content of recent meeting notes
            note_contents = []
            for note_file in recent_notes[:5]:  # Cap at 5 most recent
                content = read_file(note_file['path'])
                if content:
                    note_contents.append({
                        "filename": note_file['name'],
                        "path": note_file['path'],
                        "date": note_file.get('date'),
                        "content": content[:2000]  # Truncate long notes
                    })

            result["recent_meeting_notes"] = note_contents

        # GitHub: repo activity
        if include_repo and initiative.get('repo_path'):
            repo_path = initiative['repo_path']
            repo_activity = {}

            # Open PRs
            open_prs = _run_gh_command(
                ['gh', 'pr', 'list', '--state', 'open', '--limit', '10'],
                cwd=repo_path
            )
            if open_prs:
                repo_activity['open_prs'] = open_prs

            # Recently merged PRs
            merged_prs = _run_gh_command(
                ['gh', 'pr', 'list', '--state', 'merged', '--limit', '10'],
                cwd=repo_path
            )
            if merged_prs:
                repo_activity['merged_prs'] = merged_prs

            # Recent commits
            recent_commits = _run_gh_command(
                ['git', 'log', '--oneline', '--since=2 weeks ago'],
                cwd=repo_path
            )
            if recent_commits:
                # Truncate if very long
                lines = recent_commits.split('\n')
                if len(lines) > 30:
                    repo_activity['recent_commits'] = '\n'.join(lines[:30]) + f'\n... and {len(lines) - 30} more'
                else:
                    repo_activity['recent_commits'] = recent_commits

            # Active branches
            branches = _run_gh_command(
                ['git', 'branch', '-a', '--sort=-committerdate'],
                cwd=repo_path
            )
            if branches:
                lines = branches.split('\n')
                repo_activity['active_branches'] = '\n'.join(lines[:15])

            result["repo_activity"] = repo_activity

        return result

    except Exception as e:
        logger.error(f"get_initiative_status error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "get_initiative_status"
TOOL_DESCRIPTION = "Full status report for an initiative: DB state, team, open/completed items, Obsidian meeting notes, and optionally GitHub repo activity."
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "initiative_slug": {"type": "string", "description": "Initiative slug"},
        "include_repo": {"type": "boolean", "description": "Include GitHub repo activity via gh CLI (default false)"},
        "include_notes": {"type": "boolean", "description": "Include Obsidian meeting notes (default true)"},
        "notes_days": {"type": "integer", "description": "How many days of meeting notes to include (default 14)"}
    },
    "required": ["initiative_slug"]
}

__all__ = ['get_initiative_status', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
