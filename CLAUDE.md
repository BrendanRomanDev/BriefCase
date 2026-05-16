# BriefCase (Kit) — Development Rules

## What This Is

BriefCase is an MCP server powering **Kit**, a work-focused planning assistant for Claude Code. It provides brain dump capture, initiative tracking, daily planning, and session continuity via SQLite + Obsidian + Google Calendar MCP.

## Architecture

- **SQLite** (`~/.briefcase/briefcase.db`) — operational data: inbox (with target_week), initiatives, dailies, conversation notes
- **Obsidian** (`~/Notes/ThriveNotes/`) — unstructured knowledge: meeting notes, project docs, weekly rollups
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

## Installing & Running

First-time install on a fresh machine — one command:

```bash
./setup.sh
```

Idempotent. See `README.md` for the quick-start and `docs/INSTALL.md` for the
long-form walkthrough.

Running the MCP server standalone (rare — Claude Code spawns it):

```bash
source venv/bin/activate
python -m briefcase.mcp_server.server
```

## Project Structure

```
BriefCase/
├── setup.sh                    # One-command installer (idempotent)
├── README.md                   # Quick-start + architecture + troubleshooting
├── CLAUDE.md                   # This file (development rules)
├── CHANGELOG.md                # Version history and capability log
├── settings.yaml               # Feature flags, paths
├── .claude/commands/           # Agent instructions and skills
│   ├── kit.md                  # Main Kit agent
│   └── print-daily.md          # Print skill
├── briefcase/mcp_server/       # MCP server code
│   ├── server.py               # Entry point
│   ├── config.py               # Settings loader
│   ├── database.py             # SQLite + CRUD helpers
│   └── tools/                  # One file per MCP tool
├── briefcase/sidecar/          # FastAPI HTTP bridge for the Chrome extension
│   ├── server.py               # FastAPI app
│   ├── install.sh              # Idempotent launchd installer (called by ./setup.sh)
│   └── README.md
├── extension/                  # Chrome extension (Manifest V3, loaded unpacked)
├── scripts/
│   ├── backup-db.sh            # SQLite online-backup → ~/.briefcase/backups + iCloud
│   ├── restore-db.sh           # Restore with integrity check + safety snapshot
│   ├── restart-mcp-server.sh   # Kill the running MCP server (Claude Code re-spawns)
│   └── setup.sh                # Forwarding shim → ../setup.sh
├── docs/
│   ├── INSTALL.md              # New-machine walkthrough
│   └── user-guide.md           # Day-to-day usage
└── tests/
```
