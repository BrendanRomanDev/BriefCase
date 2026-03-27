#!/usr/bin/env python3
"""Format and print a daily checklist for thermal printer.

Usage:
  python print_daily.py                    # Print today
  python print_daily.py 2026-03-27         # Print specific date
  python print_daily.py --preview          # Preview without printing
  python print_daily.py --preview 2026-03-27
  echo "pre-formatted text" | python print_daily.py --stdin

Reads from Kit's database for tasks and formats for thermal printer output.
Calendar events should be passed via --stdin as part of a pre-formatted block,
since this script doesn't have access to Google Calendar MCP.
"""

import sys
import json
import sqlite3
import subprocess
import yaml
from datetime import datetime
from pathlib import Path


# --- Config ---

def load_config():
    settings_path = Path(__file__).parent.parent / "settings.yaml"
    if settings_path.exists():
        with open(settings_path) as f:
            return yaml.safe_load(f) or {}
    return {}


# --- DB Access ---

def get_daily_tasks(date_str: str) -> list:
    db_path = str(Path.home() / ".briefcase" / "briefcase.db")
    if not Path(db_path).exists():
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT tasks FROM dailies WHERE date = ?", (date_str,)).fetchone()
    conn.close()

    if not row:
        return []
    return json.loads(row['tasks'])


# --- Formatting ---

SEPARATOR = "─" * 32
THIN_SEP = "· " * 16


def format_header(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    day_name = dt.strftime("%A")
    formatted = dt.strftime("%B %-d, %Y")
    return f"{day_name}\n{formatted}\n{SEPARATOR}"


def format_task_item(task) -> str:
    if isinstance(task, str):
        return f"[ ] {task}"

    title = task.get('title', str(task))
    initiative = task.get('initiative', '')
    completed = task.get('completed', False)

    checkbox = "[x]" if completed else "[ ]"
    tag = f" [{initiative}]" if initiative else ""
    return f"{checkbox} {title}{tag}"


def format_event_item(event: dict) -> str:
    """Format a calendar event. Expects {time, title} or {start, title}."""
    time_str = event.get('time', event.get('start', ''))
    title = event.get('title', event.get('summary', ''))

    # Convert 24h to 12h if needed
    if time_str and ':' in time_str:
        try:
            parts = time_str.split(':')
            hour = int(parts[0])
            minute = parts[1][:2]
            if hour == 0:
                time_12 = f"12:{minute}am"
            elif hour < 12:
                time_12 = f"{hour}:{minute}am"
            elif hour == 12:
                time_12 = f"12:{minute}pm"
            else:
                time_12 = f"{hour - 12}:{minute}pm"
            return f"  {time_12}  {title}"
        except (ValueError, IndexError):
            pass

    return f"  {time_str}  {title}"


def format_daily(date_str: str, tasks: list, events: list = None) -> str:
    """Format a complete daily checklist."""
    lines = [format_header(date_str), ""]

    if events:
        lines.append("SCHEDULE")
        lines.append(THIN_SEP)
        for event in events:
            lines.append(format_event_item(event))
        lines.append("")

    if tasks:
        lines.append("TASKS")
        lines.append(THIN_SEP)
        for task in tasks:
            lines.append(format_task_item(task))
        lines.append("")

    if not tasks and not events:
        lines.append("No tasks or events planned.")
        lines.append("")

    lines.append(SEPARATOR)
    lines.append("")  # Trailing newline for printer feed

    return "\n".join(lines)


# --- Printing ---

def send_to_printer(text: str, config: dict):
    """Send formatted text to the printer."""
    printing = config.get('printing', {})
    method = printing.get('method', 'direct')

    if method == 'ssh':
        host = printing.get('ssh_host', '')
        command = printing.get('ssh_command', '')
        if not host or not command:
            print("ERROR: SSH printing configured but ssh_host or ssh_command is empty.", file=sys.stderr)
            print("Update settings.yaml with your printer connection details.", file=sys.stderr)
            sys.exit(1)

        proc = subprocess.run(
            ['ssh', host, f'{command} --stdin'],
            input=text, text=True, capture_output=True, timeout=30
        )
        if proc.returncode != 0:
            print(f"Print error: {proc.stderr}", file=sys.stderr)
            sys.exit(1)

    elif method == 'direct':
        # Direct printing — pipe to lp or a local print script
        proc = subprocess.run(
            ['lp', '-o', 'media=Custom.58x297mm'],
            input=text, text=True, capture_output=True
        )
        if proc.returncode != 0:
            print(f"Print error: {proc.stderr}", file=sys.stderr)
            sys.exit(1)

    else:
        print(f"Unknown print method: {method}", file=sys.stderr)
        sys.exit(1)

    print("Sent to printer.")


# --- Main ---

def main():
    args = sys.argv[1:]
    preview = '--preview' in args
    stdin_mode = '--stdin' in args

    if preview:
        args.remove('--preview')
    if stdin_mode:
        args.remove('--stdin')

    # If --stdin, just print/send whatever comes in on stdin
    if stdin_mode:
        text = sys.stdin.read()
        if preview:
            print(text)
        else:
            config = load_config()
            send_to_printer(text, config)
        return

    # Determine date
    date_str = args[0] if args else datetime.now().strftime("%Y-%m-%d")

    # Get tasks from DB
    tasks = get_daily_tasks(date_str)

    # Format (no events — the agent should use --stdin with pre-formatted output
    # that includes calendar events it fetched from gcal)
    output = format_daily(date_str, tasks)

    if preview:
        print(output)
    else:
        config = load_config()
        send_to_printer(output, config)


if __name__ == "__main__":
    main()
