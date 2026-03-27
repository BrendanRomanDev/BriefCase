"""MCP Tool: print_daily_list - Print daily checklist as a receipt."""

import logging
from datetime import datetime
from typing import Optional
from briefcase.mcp_server.config import load_settings
from briefcase.mcp_server.receipt_renderer import ReceiptRenderer
from briefcase.mcp_server.printer import get_printer

logger = logging.getLogger(__name__)


async def print_daily_list(
    tasks: list,
    title: Optional[str] = None,
    date: Optional[str] = None
) -> dict:
    """Print a daily checklist to the thermal printer.

    Pass clean task strings WITHOUT checkboxes — the template adds them.
    Events should be formatted as "2:00 PM - Meeting Name" (no checkbox).
    Tasks should be plain text like "Review API contract PR [insurance-management]".
    """
    try:
        settings = load_settings()

        if not settings.get('features', {}).get('printing'):
            return {"status": "error", "message": "Printing is disabled in settings.yaml (features.printing: false)"}

        printer_config = settings.get('printer', {})
        if not printer_config.get('host'):
            return {"status": "error", "message": "Printer not configured. Set printer.host in settings.yaml."}

        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        if not title:
            dt = datetime.strptime(date, "%Y-%m-%d")
            title = dt.strftime("%A, %B %-d")

        width_px = printer_config.get('width_px', 576)
        renderer = ReceiptRenderer(width_px=width_px)

        # Render template to image
        image = renderer.render_template_to_image(
            'daily_list.html',
            title=title,
            tasks=tasks
        )

        # Print
        printer = get_printer(printer_config)
        result = printer.print_image(image)

        if result['status'] == 'success':
            return {
                "status": "success",
                "message": f"Daily checklist printed: {title}",
                "title": title,
                "date": date,
                "task_count": len(tasks)
            }
        else:
            return result

    except Exception as e:
        logger.error(f"print_daily_list error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "print_daily_list"
TOOL_DESCRIPTION = "Print a daily checklist as a receipt. Pass clean task strings — the template adds checkboxes automatically."
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "tasks": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of task strings. Events: '2:00 PM - Meeting Name'. Tasks: 'Task description [initiative]'. Do NOT add checkbox characters."
        },
        "title": {"type": "string", "description": "Checklist title (defaults to formatted date)"},
        "date": {"type": "string", "description": "Date YYYY-MM-DD (defaults to today)"}
    },
    "required": ["tasks"]
}

__all__ = ['print_daily_list', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
