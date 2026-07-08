"""Briefing transcript-sync state: the freshness marker + day-window logic.

The marker is a small JSON file at ~/.briefcase/briefing_sync_state.json holding
operational state about the last transcript sync — when it ran and which meeting
dates it covered. It sits alongside sidecar_token / last_draft.txt as machine-
local operational state (NOT vault content, NOT DB rows).

The point of the marker is to answer two questions cheaply at Kit activation:
  1. Is the briefing sync STALE? (last run > threshold ago, or never)
  2. If we sync now, WHICH DATES should we scan? — "everything since the last
     sync," made weekend-aware so a Monday reach-backs to Friday rather than
     just looking at Sunday (Brendan doesn't work weekends).

All dates are local ISO dates ('YYYY-MM-DD'). Timestamps are local ISO too. This
is deliberately not UTC — the "have 12 hours passed", "is it Monday", and "which
working days did I miss" questions are all about Brendan's local wall clock.
"""

import json
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional

STATE_PATH = Path.home() / ".briefcase" / "briefing_sync_state.json"

# How long since the last sync before we consider the briefing stale.
STALE_AFTER_HOURS = 12

# Weekend weekday numbers (Mon=0 .. Sun=6).
_WEEKEND = {5, 6}

# First-run default: how many working days back to scan when there's no marker
# at all (so we don't try to scan all of history on first setup).
FIRST_RUN_WORKING_DAYS = 1


def _is_weekend(d: date) -> bool:
    return d.weekday() in _WEEKEND


def _working_days_between(start_exclusive: date, end_inclusive: date) -> list:
    """Working days (Mon-Fri) in (start_exclusive, end_inclusive]. Empty if the
    range is empty or contains only weekend days."""
    days = []
    cur = start_exclusive + timedelta(days=1)
    while cur <= end_inclusive:
        if not _is_weekend(cur):
            days.append(cur.isoformat())
        cur += timedelta(days=1)
    return days


def _last_n_working_days(end_inclusive: date, n: int) -> list:
    """The n most recent working days up to and including end_inclusive (if it's
    a working day). Used for the first-run default window."""
    days = []
    cur = end_inclusive
    while len(days) < n and cur > end_inclusive - timedelta(days=14):  # safety bound
        if not _is_weekend(cur):
            days.append(cur.isoformat())
        cur -= timedelta(days=1)
    return sorted(days)


def read_state() -> Optional[dict]:
    """Return the raw marker dict, or None if no sync has ever run."""
    if not STATE_PATH.exists():
        return None
    try:
        return json.loads(STATE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def write_state(last_sync_iso: str, dates_covered: list,
                meetings_scanned: int = None,
                not_recorded: list = None) -> dict:
    """Persist a completed sync. Returns the written dict."""
    state = {
        "last_sync": last_sync_iso,
        "dates_covered": sorted(set(dates_covered or [])),
        "meetings_scanned": meetings_scanned,
        "not_recorded": not_recorded or [],
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))
    return state


def compute_window(now: datetime, state: Optional[dict]) -> dict:
    """Given the current local time and the marker, compute what a sync should
    scan and whether it's stale.

    Returns:
      {
        "is_stale": bool,               # should we proactively sync?
        "hours_since": float | None,    # None if never synced
        "last_sync": str | None,
        "last_covered": [str],          # dates the last sync covered
        "scan_dates": [str],            # working-day dates to scan now
        "reason": str,                  # human-readable window explanation
        "first_run": bool,
      }
    """
    today = now.date()

    if state is None:
        scan = _last_n_working_days(today, FIRST_RUN_WORKING_DAYS)
        # If today is a weekend and there are no working days in the last-N,
        # fall back to the most recent working day before today.
        if not scan:
            scan = _last_n_working_days(today - timedelta(days=1), 1)
        return {
            "is_stale": True,
            "hours_since": None,
            "last_sync": None,
            "last_covered": [],
            "scan_dates": scan,
            "reason": (f"First run — no prior sync marker. Defaulting to the last "
                       f"{FIRST_RUN_WORKING_DAYS} working day(s): {scan or 'none'}. "
                       f"Tell Kit explicit dates to override."),
            "first_run": True,
        }

    last_sync_iso = state.get("last_sync")
    try:
        last_sync_dt = datetime.fromisoformat(last_sync_iso) if last_sync_iso else None
    except ValueError:
        last_sync_dt = None

    hours_since = None
    if last_sync_dt is not None:
        hours_since = (now - last_sync_dt).total_seconds() / 3600.0

    # The last date we already covered — scan working days AFTER that up to today.
    covered = state.get("dates_covered") or []
    if covered:
        try:
            last_covered_date = date.fromisoformat(max(covered))
        except ValueError:
            last_covered_date = (last_sync_dt.date() if last_sync_dt else today) - timedelta(days=1)
    else:
        last_covered_date = (last_sync_dt.date() if last_sync_dt else today) - timedelta(days=1)

    scan = _working_days_between(last_covered_date, today)

    is_stale = (hours_since is None) or (hours_since >= STALE_AFTER_HOURS)
    # If there are no new working days to scan (e.g. synced earlier today, or it's
    # the weekend with nothing new), it's not actually stale regardless of hours.
    if not scan:
        is_stale = False

    if scan:
        span = f"{scan[0]}" if len(scan) == 1 else f"{scan[0]}–{scan[-1]}"
        reason = (f"Last sync {last_sync_iso} covered through {last_covered_date.isoformat()}. "
                  f"Working days since: {span} ({len(scan)} day(s)).")
        if today.weekday() == 0 and any(date.fromisoformat(d).weekday() == 4 for d in scan):
            reason += " (Monday reach-back includes Friday — weekend skipped.)"
    else:
        reason = (f"Nothing new to scan — last sync covered through "
                  f"{last_covered_date.isoformat()} and there are no working days since.")

    return {
        "is_stale": is_stale,
        "hours_since": round(hours_since, 1) if hours_since is not None else None,
        "last_sync": last_sync_iso,
        "last_covered": covered,
        "scan_dates": scan,
        "reason": reason,
        "first_run": False,
    }
