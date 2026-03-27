"""MCP Tool: print_custom - Print any markdown-formatted content as a receipt."""

import re
import logging
from datetime import datetime
from typing import Optional
from briefcase.mcp_server.config import load_settings
from briefcase.mcp_server.receipt_renderer import ReceiptRenderer
from briefcase.mcp_server.printer import get_printer

logger = logging.getLogger(__name__)


def _markdown_to_html(text: str) -> str:
    """Convert simple markdown to HTML for receipt rendering."""
    lines = text.split('\n')
    html_lines = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            html_lines.append('<div style="margin: 8px 0;"></div>')
            continue

        # Bold: **text**
        stripped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', stripped)

        # Checkboxes: □ item or - [ ] item
        stripped = re.sub(r'^[□☐]\s*', '☐ ', stripped)
        stripped = re.sub(r'^- \[ \]\s*', '☐ ', stripped)
        stripped = re.sub(r'^- \[x\]\s*', '☑ ', stripped)

        # Bullets: • item or - item (but not - [ ])
        if re.match(r'^[-•]\s+(?!\[)', stripped):
            stripped = re.sub(r'^[-•]\s+', '• ', stripped)

        html_lines.append(f'<div>{stripped}</div>')

    return '\n'.join(html_lines)


async def print_custom(
    content: str,
    title: Optional[str] = None
) -> dict:
    """Print any markdown-formatted content as a receipt.

    Use for: meeting agendas, project checklists, grocery lists, notes,
    or any custom formatted content.
    """
    try:
        settings = load_settings()

        if not settings.get('features', {}).get('printing'):
            return {"status": "error", "message": "Printing is disabled in settings.yaml (features.printing: false)"}

        printer_config = settings.get('printer', {})
        if not printer_config.get('host'):
            return {"status": "error", "message": "Printer not configured. Set printer.host in settings.yaml."}

        timestamp = datetime.now().strftime("%-I:%M %p, %B %-d, %Y")

        # Convert markdown to HTML
        html_content = _markdown_to_html(content)

        width_px = printer_config.get('width_px', 576)
        renderer = ReceiptRenderer(width_px=width_px)

        # Render template to image
        image = renderer.render_template_to_image(
            'custom_content.html',
            title=title,
            content=html_content,
            timestamp=timestamp
        )

        # Print
        printer = get_printer(printer_config)
        result = printer.print_image(image)

        if result['status'] == 'success':
            line_count = len(content.strip().split('\n'))
            return {
                "status": "success",
                "message": f"Custom content printed{f': {title}' if title else ''}",
                "title": title,
                "line_count": line_count
            }
        else:
            return result

    except Exception as e:
        logger.error(f"print_custom error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "print_custom"
TOOL_DESCRIPTION = "Print any markdown-formatted content as a receipt. Supports bold, checkboxes, and bullets."
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "content": {"type": "string", "description": "Markdown-formatted content to print"},
        "title": {"type": "string", "description": "Optional title for the receipt header"}
    },
    "required": ["content"]
}

__all__ = ['print_custom', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
