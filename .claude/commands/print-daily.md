Generate and print today's daily checklist to the thermal printer.

## Steps

### 1. Gather Data

Run these in parallel:
- `query_daily(date=today)` — get tasks from Kit's database
- `gcal_list_events` for today — get calendar events (Google Calendar MCP)

### 2. Build the Task List

Combine events and tasks into a single array of strings for `print_daily_list`:

**Events** (no checkbox — informational):
- Format: `"9:00 AM - Standup"`
- Format: `"1:30 PM - Insurance Review"`
- ALWAYS 12-hour time

**Blank separator between events and tasks:**
- Add an empty string `""` between the events section and tasks section

**Tasks** (checkbox added by template):
- Format: `"Review API contract PR [insurance-management]"`
- Format: `"Respond to Akash on migration question"`
- Tag with `[initiative-slug]` if linked
- Sort by urgency (ASAP first)

### 3. Preview

Show the proposed list to Brendan. Ask "Send to printer?" before printing.

### 4. Print

Call `print_daily_list(tasks=combined_list, date=today)`.

The tool handles rendering to HTML, converting to image, and sending to the network printer at 192.168.68.99.

### Edge Cases

- **No tasks or events:** Tell Brendan there's nothing to print.
- **Events only:** Print just the events list.
- **Tasks only:** Print just the tasks list.
- **Printer offline:** The tool will return an error — suggest checking the printer connection.
