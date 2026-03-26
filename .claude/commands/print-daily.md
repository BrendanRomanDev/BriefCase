Generate and print today's daily checklist.

## Steps

1. Read today's daily plan: `query_daily(date=today)`
2. Pull today's calendar events: `gcal_list_events` for today
3. Format for thermal printer:
   - Header: date, day of week
   - Calendar events: time in 12-hour format, title. NO checkboxes (events are informational).
   - Tasks: checkbox + title, tagged with initiative if linked
   - Separator between events and tasks sections
4. Send to printer (via SSH or direct, based on settings.yaml)

## Formatting Rules

- 12-hour time format always (never 24-hour)
- No checkboxes for events (time-bound, informational)
- Checkboxes `[ ]` for tasks
- Tag tasks with `[initiative-slug]` if linked
- Keep it compact — thermal printer paper is narrow

## Print Command

Check `settings.yaml` for print method:
- If `method: ssh` — run: `ssh {ssh_host} "{ssh_command} --stdin"` and pipe the formatted text
- If `method: direct` — run the print script locally
