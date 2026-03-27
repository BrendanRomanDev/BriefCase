Generate and print today's daily checklist to the thermal printer.

## Steps

### 1. Gather Data

Run these in parallel:
- `query_daily(date=today)` — get tasks from Kit's database
- `gcal_list_events` for today — get calendar events (Google Calendar MCP)

### 2. Format the Output

Build a plain text checklist following this exact format:

```
{Day of Week}
{Month Day, Year}
────────────────────────────────

SCHEDULE
· · · · · · · · · · · · · · · ·
  {time}  {event title}
  {time}  {event title}

TASKS
· · · · · · · · · · · · · · · ·
[ ] {task title} [{initiative}]
[ ] {task title}
[x] {completed task}

────────────────────────────────
```

### Formatting Rules

- **Time:** Always 12-hour format (9:00am, 1:30pm). Never 24-hour.
- **Events:** Indented with time, NO checkboxes. Events are informational, not actionable.
- **Tasks:** `[ ]` checkbox prefix. Tag with `[slug]` if linked to an initiative. `[x]` if already completed.
- **Order:** Events sorted by time. Tasks sorted by urgency (ASAP first).
- **Width:** Keep lines under 32 characters when possible (thermal paper is narrow). Wrap long titles if needed.
- **No emoji.** Plain text only.

### 3. Preview

Show the formatted output to Brendan first. Ask "Send to printer?" before printing.

### 4. Print

Pipe the formatted text to the print script:

```bash
echo "{formatted_text}" | python3 /Users/brendan.roman/Programming/BriefCase/scripts/print_daily.py --stdin
```

Or for preview only (no actual printing):
```bash
echo "{formatted_text}" | python3 /Users/brendan.roman/Programming/BriefCase/scripts/print_daily.py --stdin --preview
```

The print script reads `settings.yaml` to determine whether to use SSH or direct printing.

### Edge Cases

- **No tasks or events:** Print a simple header with "No tasks or events planned."
- **Events only (no tasks):** Skip the TASKS section.
- **Tasks only (no events):** Skip the SCHEDULE section.
- **Past events:** Include them but don't flag them — the printed checklist is a reference, not a live tracker.
