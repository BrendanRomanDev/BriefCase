# BriefCase (Kit) — Development Rules

## What This Is

BriefCase is an MCP server powering **Kit**, a work-focused planning assistant for Claude Code. It provides brain dump capture, initiative tracking, daily planning, and session continuity via SQLite + Obsidian + Google Calendar MCP.

## Architecture

- **SQLite** (`~/.briefcase/briefcase.db`) — operational data: inbox, initiatives, dailies, conversation notes
- **Obsidian** (`~/Notes/ThriveNotes/`) — unstructured knowledge: meeting notes, project docs
- **Google Calendar MCP** — event source of truth (separate MCP, NOT part of this server)
- **Kit agent** (`.claude/commands/kit.md`) — orchestrates all three

## Critical Rules

### Dual Instruction Sync

Kit receives instructions from TWO places that MUST stay in sync:

1. `.claude/commands/kit.md` — full agent instructions
2. `briefcase/mcp_server/server.py` — `SERVER_INSTRUCTIONS` sent to all MCP clients

When changing behavior, update BOTH files.

### Tools-First

Use MCP tools, not resources. Resources don't work in Claude Code CLI. All context loading happens via tool calls at conversation start.

### Events Stay in Google Calendar

The `dailies` table stores **tasks only**. Calendar events are read by the agent at runtime via `gcal_list_events` and presented alongside tasks. Never store events in the database.

### Time Awareness

`get_forecast()` includes current time in its output. Without this, the agent can't determine if events have passed or are upcoming.

### Tool File Pattern

Each tool is one file in `briefcase/mcp_server/tools/`. It exports:
- `async def tool_name(...)` — the handler
- `TOOL_NAME` — string
- `TOOL_DESCRIPTION` — string
- `TOOL_SCHEMA` — JSON schema dict

Register in `server.py` via the generator pattern (`_import_*_tools` functions).

## Running the Server

```bash
cd /Users/brendan.roman/Programming/BriefCase
source venv/bin/activate
python -m briefcase.mcp_server.server
```

## Project Structure

```
briefcase/
├── CLAUDE.md                   # This file
├── .claude/commands/           # Agent instructions and skills
│   ├── kit.md                  # Main Kit agent
│   └── print-daily.md          # Print skill
├── briefcase/mcp_server/       # MCP server code
│   ├── server.py               # Entry point
│   ├── config.py               # Settings loader
│   ├── database.py             # SQLite + CRUD helpers
│   └── tools/                  # One file per MCP tool
├── scripts/                    # Setup and utility scripts
├── settings.yaml               # Feature flags, paths
└── tests/
```
