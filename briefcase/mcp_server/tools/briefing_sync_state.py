"""MCP Tool: briefing_sync_state - freshness marker + day-window for the
transcript sync.

Kit calls this at activation to decide whether to proactively dispatch a
transcript sync (and which meeting dates to scan), and the sync sub-agent calls
it when done to record that a sync completed.

Two actions:
  action='get' (default) — returns staleness + the weekend-aware scan window:
    is_stale, hours_since, last_sync, last_covered, scan_dates, reason, first_run.
    Kit uses is_stale to decide whether to silently dispatch the sync, and
    scan_dates to tell the sync sub-agent exactly which days to pull.
  action='record' — mark a sync complete. Pass dates_covered (the meeting dates
    actually scanned), optionally meetings_scanned and not_recorded (titles of
    meetings that had no Gemini transcript). Updates the marker so the next
    'get' computes the correct next window.

The window logic is weekend-aware: on Monday, "everything since the last sync"
correctly reaches back to Friday (Brendan doesn't work Sat/Sun). First run with
no marker defaults to a small window rather than scanning all of history.
"""

import logging
from datetime import datetime
from typing import Optional

from briefcase.mcp_server.sync_state import (
    read_state, write_state, compute_window, STALE_AFTER_HOURS,
)

logger = logging.getLogger(__name__)


async def briefing_sync_state(
    action: str = "get",
    dates_covered: Optional[list] = None,
    meetings_scanned: Optional[int] = None,
    not_recorded: Optional[list] = None,
) -> dict:
    """Read (get) or update (record) the transcript-sync freshness marker."""
    try:
        now = datetime.now()

        if action == "get":
            state = read_state()
            window = compute_window(now, state)
            window["status"] = "success"
            window["stale_after_hours"] = STALE_AFTER_HOURS
            window["now"] = now.isoformat(timespec="seconds")
            return window

        if action == "record":
            if not dates_covered:
                return {
                    "status": "error",
                    "message": "action='record' requires dates_covered (the meeting dates scanned).",
                }
            written = write_state(
                last_sync_iso=now.isoformat(timespec="seconds"),
                dates_covered=dates_covered,
                meetings_scanned=meetings_scanned,
                not_recorded=not_recorded,
            )
            written["status"] = "success"
            return written

        return {"status": "error", "message": f"Unknown action '{action}'. Use 'get' or 'record'."}

    except Exception as e:
        logger.error(f"briefing_sync_state error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "briefing_sync_state"
TOOL_DESCRIPTION = (
    "Freshness marker + day-window for the briefing transcript sync. action='get' (default) "
    "returns whether the sync is stale (last run > threshold or never) and which meeting "
    "dates to scan now — 'everything since the last sync', weekend-aware so Monday reaches "
    "back to Friday, first-run defaults to a small window. Kit calls this at activation to "
    "decide whether to silently dispatch a sync. action='record' marks a sync complete "
    "(pass dates_covered, optionally meetings_scanned + not_recorded) so the next 'get' "
    "computes the right next window."
)
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["get", "record"],
            "description": "'get' (default) reads staleness + scan window. 'record' marks a sync done.",
        },
        "dates_covered": {
            "type": "array",
            "items": {"type": "string"},
            "description": "action='record': the meeting dates actually scanned (ISO 'YYYY-MM-DD').",
        },
        "meetings_scanned": {
            "type": "integer",
            "description": "action='record': how many meetings were read (optional).",
        },
        "not_recorded": {
            "type": "array",
            "items": {"type": "string"},
            "description": "action='record': titles of meetings that had no Gemini transcript (optional).",
        },
    },
}

__all__ = ['briefing_sync_state', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
