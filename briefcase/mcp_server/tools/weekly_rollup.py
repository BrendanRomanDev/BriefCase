"""MCP Tool: weekly_rollup - Generate a weekly executive summary to Obsidian.

Gathers from DB (dailies, conversation notes, inbox) and Obsidian (meeting
notes filed that week), plus a look-ahead (target_week items and approaching
deadlines), and writes a rollup markdown file to `weeklies/<iso-week>-rollup.md`
in the Obsidian vault.
"""

import logging
import os
import re
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional

from briefcase.mcp_server.database import (
    get_db_connection, get_all_initiatives, get_recent_conversation_notes,
)
from briefcase.mcp_server.obsidian import (
    get_vault_path, write_file, read_file,
)

logger = logging.getLogger(__name__)


def _iso_week_to_range(iso_week: str) -> tuple[date, date]:
    """Convert '2026-W15' to (monday, sunday) dates."""
    match = re.match(r"^(\d{4})-W(\d{1,2})$", iso_week.strip())
    if not match:
        raise ValueError(f"target_week must be ISO format like '2026-W15' (got '{iso_week}')")
    year, week = int(match.group(1)), int(match.group(2))
    monday = date.fromisocalendar(year, week, 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _current_iso_week() -> str:
    today = date.today()
    iso_year, iso_week, _ = today.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _shift_iso_week(iso_week: str, weeks: int) -> str:
    monday, _ = _iso_week_to_range(iso_week)
    shifted = monday + timedelta(weeks=weeks)
    iso_year, iso_w, _ = shifted.isocalendar()
    return f"{iso_year}-W{iso_w:02d}"


def _collect_meeting_notes(vault: Path, week_start: date, week_end: date) -> list[dict]:
    """Find meeting notes in Projects/*/meetings/ and Meetings/general/ whose
    filename date prefix falls within [week_start, week_end]."""
    start_str = week_start.isoformat()
    end_str = week_end.isoformat()
    found = []

    candidate_dirs = []
    projects_dir = vault / "Projects"
    if projects_dir.exists():
        for proj in projects_dir.iterdir():
            meetings = proj / "meetings"
            if meetings.is_dir():
                candidate_dirs.append(("project:" + proj.name, meetings))

    general = vault / "Meetings" / "general"
    if general.is_dir():
        candidate_dirs.append(("general", general))

    for scope, dir_path in candidate_dirs:
        for f in dir_path.iterdir():
            if not f.is_file() or f.suffix != ".md" or f.name.startswith("."):
                continue
            m = re.match(r"^(\d{4}-\d{2}-\d{2})", f.name)
            if not m:
                continue
            file_date = m.group(1)
            if start_str <= file_date <= end_str:
                content = f.read_text(encoding="utf-8", errors="replace")
                found.append({
                    "scope": scope,
                    "date": file_date,
                    "filename": f.name,
                    "relative_path": str(f.relative_to(vault)),
                    "excerpt": content[:1500],
                })

    found.sort(key=lambda x: (x["date"], x["filename"]))
    return found


def _format_rollup_md(iso_week: str, week_start: date, week_end: date,
                     data: dict) -> str:
    """Render the rollup as markdown. Concise — Brendan can flesh it out later."""
    lines = [
        f"# Weekly Rollup — {iso_week}",
        f"_{week_start.isoformat()} → {week_end.isoformat()}_",
        f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
        "## Meetings & Decisions",
    ]

    if data["meeting_notes"]:
        for note in data["meeting_notes"]:
            lines.append(f"- **{note['date']}** [[{note['relative_path']}|{note['filename']}]]  _(scope: {note['scope']})_")
    else:
        lines.append("_No meeting notes filed this week._")

    lines += ["", "## Work Completed", ""]
    completed = data["completed_tasks"]
    if completed:
        by_initiative = {}
        for t in completed:
            key = t.get("initiative_slug") or "(uncategorized)"
            by_initiative.setdefault(key, []).append(t)
        for slug, tasks in sorted(by_initiative.items()):
            lines.append(f"### {slug}")
            for t in tasks:
                lines.append(f"- {t['title']}")
            lines.append("")
    else:
        lines.append("_No tasks completed this week._")
        lines.append("")

    lines += ["## Open Threads", ""]
    open_items = data["open_inbox_created"]
    if open_items:
        for t in open_items[:25]:
            slug = t.get("initiative_slug") or "—"
            lines.append(f"- [{slug}] {t['title']}")
    else:
        lines.append("_No new open items captured this week._")
    lines.append("")

    lines += ["## Look Ahead", ""]
    lookahead = data["look_ahead"]
    if lookahead["targeted_items"]:
        lines.append("**Targeted for upcoming weeks:**")
        for t in lookahead["targeted_items"]:
            lines.append(f"- [{t.get('target_week')}] {t['title']}")
        lines.append("")
    if lookahead["approaching_deadlines"]:
        lines.append("**Approaching initiative deadlines:**")
        for d in lookahead["approaching_deadlines"]:
            lines.append(f"- {d['name']} ({d['slug']}) — {d['deadline']} ({d['days_out']}d)")
        lines.append("")
    if not lookahead["targeted_items"] and not lookahead["approaching_deadlines"]:
        lines.append("_Nothing scheduled or approaching._")
        lines.append("")

    lines += ["## Session Context", ""]
    if data["conversation_notes"]:
        for n in data["conversation_notes"]:
            created = n.get("created_at", "")[:10]
            summary = (n.get("summary") or "").strip()
            if summary:
                lines.append(f"- **{created}** — {summary[:300]}")
    else:
        lines.append("_No conversation notes from this week._")
    lines.append("")

    return "\n".join(lines)


async def weekly_rollup(
    target_week: Optional[str] = None,
    lookahead_weeks: int = 2,
    overwrite: bool = False,
) -> dict:
    """Generate a weekly rollup and write it to ThriveNotes/weeklies/."""
    try:
        if target_week is None:
            target_week = _current_iso_week()

        week_start, week_end = _iso_week_to_range(target_week)
        start_iso = week_start.isoformat()
        end_iso = week_end.isoformat()
        end_inclusive = end_iso + "T23:59:59"

        relative_path = f"weeklies/{target_week}-rollup.md"
        vault = get_vault_path()
        target_file = vault / relative_path

        if target_file.exists() and not overwrite:
            existing = read_file(relative_path)
            return {
                "status": "exists",
                "message": f"Rollup already exists at {relative_path}. Pass overwrite=true to regenerate.",
                "iso_week": target_week,
                "path": str(target_file),
                "existing_preview": (existing or "")[:600],
            }

        conn = get_db_connection()
        try:
            # Tasks completed this week (join to initiatives for slug)
            completed_rows = conn.execute(
                """SELECT i.id, i.title, i.completed_at, init.slug AS initiative_slug
                   FROM inbox i
                   LEFT JOIN initiatives init ON init.id = i.initiative_id
                   WHERE i.completed_at BETWEEN ? AND ?
                   ORDER BY i.completed_at""",
                (start_iso, end_inclusive)
            ).fetchall()
            completed_tasks = [dict(r) for r in completed_rows]

            # Open items created this week
            open_rows = conn.execute(
                """SELECT i.id, i.title, i.target_week, i.created_at,
                          init.slug AS initiative_slug
                   FROM inbox i
                   LEFT JOIN initiatives init ON init.id = i.initiative_id
                   WHERE i.created_at BETWEEN ? AND ?
                   AND i.completed_at IS NULL
                   AND i.status != 'discarded'
                   ORDER BY i.created_at""",
                (start_iso, end_inclusive)
            ).fetchall()
            open_inbox_created = [dict(r) for r in open_rows]

            # Conversation notes from this week
            note_rows = conn.execute(
                """SELECT id, summary, next_intentions, topics, created_at
                   FROM conversation_notes
                   WHERE created_at BETWEEN ? AND ?
                   ORDER BY created_at""",
                (start_iso, end_inclusive)
            ).fetchall()
            conversation_notes = [dict(r) for r in note_rows]

            # Look ahead: target_week items for next N weeks
            future_weeks = [_shift_iso_week(target_week, i) for i in range(1, lookahead_weeks + 1)]
            placeholders = ",".join(["?"] * len(future_weeks))
            targeted_rows = conn.execute(
                f"""SELECT i.title, i.target_week, init.slug AS initiative_slug
                    FROM inbox i
                    LEFT JOIN initiatives init ON init.id = i.initiative_id
                    WHERE i.target_week IN ({placeholders})
                    AND i.completed_at IS NULL
                    AND i.status != 'discarded'
                    ORDER BY i.target_week, i.urgency DESC""",
                future_weeks
            ).fetchall() if future_weeks else []
            targeted_items = [dict(r) for r in targeted_rows]

            # Approaching deadlines within the look-ahead window
            today = date.today()
            window_end = today + timedelta(weeks=lookahead_weeks)
            initiatives = get_all_initiatives(conn)
            approaching = []
            for init in initiatives:
                deadline = init.get("deadline")
                if not deadline:
                    continue
                try:
                    d = date.fromisoformat(deadline[:10])
                except ValueError:
                    continue
                if today <= d <= window_end:
                    approaching.append({
                        "slug": init["slug"],
                        "name": init["name"],
                        "deadline": deadline,
                        "days_out": (d - today).days,
                    })
            approaching.sort(key=lambda x: x["deadline"])

        finally:
            conn.close()

        meeting_notes = _collect_meeting_notes(vault, week_start, week_end)

        data = {
            "completed_tasks": completed_tasks,
            "open_inbox_created": open_inbox_created,
            "conversation_notes": conversation_notes,
            "meeting_notes": meeting_notes,
            "look_ahead": {
                "targeted_items": targeted_items,
                "approaching_deadlines": approaching,
            },
        }

        md = _format_rollup_md(target_week, week_start, week_end, data)
        written_path = write_file(relative_path, md, append=False)

        return {
            "status": "success",
            "iso_week": target_week,
            "week_start": start_iso,
            "week_end": end_iso,
            "path": written_path,
            "relative_path": relative_path,
            "counts": {
                "meeting_notes": len(meeting_notes),
                "completed_tasks": len(completed_tasks),
                "open_inbox_created": len(open_inbox_created),
                "conversation_notes": len(conversation_notes),
                "targeted_lookahead": len(targeted_items),
                "approaching_deadlines": len(approaching),
            },
            "preview": md[:800],
        }

    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.error(f"weekly_rollup error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "weekly_rollup"
TOOL_DESCRIPTION = (
    "Generate a weekly executive summary covering meetings (Obsidian), completed/open "
    "work (DB), conversation notes, and a look-ahead (target_week items + approaching "
    "deadlines). Writes to ThriveNotes/weeklies/<iso-week>-rollup.md. Defaults to the "
    "current ISO week."
)
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "target_week": {
            "type": "string",
            "description": "ISO week to roll up (e.g., '2026-W15'). Defaults to current week."
        },
        "lookahead_weeks": {
            "type": "integer", "default": 2,
            "description": "How many future weeks to scan for targeted items and approaching deadlines"
        },
        "overwrite": {
            "type": "boolean", "default": False,
            "description": "If a rollup file already exists, regenerate it instead of returning the existing one"
        },
    }
}

__all__ = ['weekly_rollup', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
