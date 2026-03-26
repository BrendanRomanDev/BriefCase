"""MCP Tool: get_forecast - Database-side big-picture view."""

import logging
from datetime import datetime, timedelta, UTC
from briefcase.mcp_server.database import (
    get_db_connection, get_all_initiatives, get_inbox_items,
    get_recent_conversation_notes
)

logger = logging.getLogger(__name__)


async def get_forecast(days: int = 14) -> dict:
    """The database-side big-picture view. Returns initiative deadlines,
    high-priority inbox items, and recent conversation notes.

    NOTE: This does NOT include calendar events. The agent calls
    gcal_list_events separately and merges the results."""
    try:
        conn = get_db_connection()
        now = datetime.now(UTC)
        window_end = (now + timedelta(days=days)).strftime("%Y-%m-%d")
        today = now.strftime("%Y-%m-%d")

        # Initiative deadlines within the window
        all_initiatives = get_all_initiatives(conn, status='active')
        approaching_deadlines = []
        for init in all_initiatives:
            if init.get('deadline') and init['deadline'] <= window_end:
                days_until = (datetime.strptime(init['deadline'], "%Y-%m-%d").date() - now.date()).days
                approaching_deadlines.append({
                    "name": init['name'],
                    "slug": init['slug'],
                    "deadline": init['deadline'],
                    "days_until": days_until,
                    "overdue": days_until < 0
                })

        approaching_deadlines.sort(key=lambda x: x['days_until'])

        # High-priority inbox items (urgency >= 3 or complexity >= 2 and unscheduled)
        all_items = get_inbox_items(conn)
        high_priority = [
            item for item in all_items
            if item.get('urgency', 1) >= 3 or (item.get('complexity', 1) >= 2 and item.get('status') != 'scheduled')
        ]

        # Overdue scheduled items
        overdue = [
            item for item in all_items
            if item.get('scheduled_at') and item['scheduled_at'] < today and item.get('status') == 'scheduled'
        ]

        # Recent conversation notes for continuity
        notes = get_recent_conversation_notes(conn, days=2)

        conn.close()

        # Format current time prominently
        current_time = now.strftime("%-I:%M %p on %A, %B %-d, %Y")

        return {
            "status": "success",
            "current_time": current_time,
            "forecast_window": f"{today} to {window_end}",
            "approaching_deadlines": approaching_deadlines,
            "high_priority_items": high_priority,
            "overdue_items": overdue,
            "recent_conversation_notes": notes,
            "note": "Calendar events are NOT included here. Call gcal_list_events separately."
        }
    except Exception as e:
        logger.error(f"get_forecast error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "get_forecast"
TOOL_DESCRIPTION = "Database-side big-picture view: initiative deadlines, high-priority inbox items, recent session notes. Does NOT include calendar events - the agent calls gcal_list_events separately."
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "days": {"type": "integer", "default": 14,
                 "description": "Forecast window in days (default 14)"}
    }
}

__all__ = ['get_forecast', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
