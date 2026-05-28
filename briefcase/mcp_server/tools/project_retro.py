"""MCP Tool: project_retro - Week-by-week retrospective for an initiative."""

import logging
import subprocess
from datetime import datetime, timedelta
from typing import Optional
from briefcase.mcp_server.database import (
    get_db_connection, get_initiative_by_slug
)
from briefcase.mcp_server.obsidian import (
    list_files, read_file, get_meetings_folder
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


def _get_week_ranges(weeks: int) -> list[dict]:
    """Generate Monday-to-Sunday date ranges for the last N weeks."""
    today = datetime.now().date()
    # Find the most recent Monday
    current_monday = today - timedelta(days=today.weekday())

    ranges = []
    for i in range(weeks):
        week_start = current_monday - timedelta(weeks=i)
        week_end = week_start + timedelta(days=6)
        ranges.append({
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "label": f"Week of {week_start.strftime('%b %-d')}"
        })

    ranges.reverse()  # Chronological order
    return ranges


async def project_retro(
    initiative_slug: str,
    weeks: int = 4
) -> dict:
    """Generate a week-by-week retrospective pulling from DB, Obsidian, and gh CLI."""
    try:
        conn = get_db_connection()
        initiative = get_initiative_by_slug(conn, initiative_slug)

        if not initiative:
            conn.close()
            return {"status": "error", "message": f"Initiative '{initiative_slug}' not found"}

        week_ranges = _get_week_ranges(weeks)
        meetings_folder = get_meetings_folder(initiative_slug)
        all_meeting_files = list_files(meetings_folder)
        repo_path = initiative.get('repo_path')

        weekly_data = []

        for week in week_ranges:
            week_start = week['week_start']
            week_end = week['week_end']
            week_entry = {
                "label": week['label'],
                "week_start": week_start,
                "week_end": week_end,
            }

            # DB: tasks completed this week
            completed = conn.execute(
                """SELECT title, completed_at FROM inbox
                   WHERE initiative_id = ?
                   AND completed_at BETWEEN ? AND ?
                   ORDER BY completed_at""",
                (initiative['id'], week_start, week_end + 'T23:59:59')
            ).fetchall()
            week_entry['completed_tasks'] = [dict(row) for row in completed]

            # DB: conversation notes from this week
            notes = conn.execute(
                """SELECT summary, topics, created_at FROM conversation_notes
                   WHERE created_at BETWEEN ? AND ?
                   ORDER BY created_at""",
                (week_start, week_end + 'T23:59:59')
            ).fetchall()
            week_entry['conversation_notes'] = [dict(row) for row in notes]

            # Obsidian: meeting notes filed this week (match date prefix)
            week_meetings = []
            for f in all_meeting_files:
                name = f['name']
                if name >= week_start and name <= week_end + 'z':
                    content = read_file(f['path'])
                    week_meetings.append({
                        "filename": name,
                        "content": content[:1500] if content else None
                    })
            week_entry['meeting_notes'] = week_meetings

            # GitHub: repo activity this week
            if repo_path:
                commits = _run_command(
                    ['git', 'log', '--oneline',
                     f'--since={week_start}', f'--until={week_end}'],
                    cwd=repo_path
                )
                if commits:
                    lines = commits.split('\n')
                    week_entry['commit_count'] = len(lines)
                    week_entry['commits'] = '\n'.join(lines[:15])
                else:
                    week_entry['commit_count'] = 0

                merged = _run_command(
                    ['gh', 'pr', 'list', '--state', 'merged',
                     '--search', f'merged:{week_start}..{week_end}', '--limit', '10'],
                    cwd=repo_path
                )
                if merged:
                    week_entry['merged_prs'] = merged
            else:
                week_entry['commit_count'] = 0

            weekly_data.append(week_entry)

        conn.close()

        # Compute simple velocity trend
        task_counts = [len(w['completed_tasks']) for w in weekly_data]
        commit_counts = [w.get('commit_count', 0) for w in weekly_data]

        return {
            "status": "success",
            "initiative": {
                "name": initiative['name'],
                "slug": initiative['slug'],
                "status": initiative['status'],
                "deadline": initiative.get('deadline'),
            },
            "period": f"{week_ranges[0]['week_start']} to {week_ranges[-1]['week_end']}",
            "weeks": weeks,
            "weekly_data": weekly_data,
            "velocity_summary": {
                "tasks_completed_per_week": task_counts,
                "commits_per_week": commit_counts,
            },
            "formatting_instructions": (
                "Format as a week-by-week retrospective. For each week show: "
                "meeting notes filed, tasks completed, repo activity (PRs merged, commits). "
                "End with a Trends & Observations section covering velocity, recurring blockers, "
                "scope changes, and team dynamics. Add 1-3 actionable recommendations. "
                "Offer to save the retro to the vault and brain dump any action items."
            )
        }

    except Exception as e:
        logger.error(f"project_retro error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "project_retro"
TOOL_DESCRIPTION = "Generate a week-by-week retrospective for an initiative: meeting notes, completed tasks, repo activity, and velocity trends."
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "initiative_slug": {"type": "string", "description": "Initiative slug"},
        "weeks": {"type": "integer", "default": 4,
                 "description": "Number of weeks to cover (default 4)"}
    },
    "required": ["initiative_slug"]
}

__all__ = ['project_retro', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
