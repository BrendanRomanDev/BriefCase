# BriefCase (Kit) — Design Brief

**Status:** Phase 1 built and operational
**Created:** 2026-03-26
**Origin:** Forge brainstorm session — Brendan inheriting PM responsibilities at Thriveworks

---

## What This Is

**Kit** is a standalone MCP-powered planning assistant for Brendan's work at Thriveworks. It provides brain dump capture, initiative tracking, daily planning, meeting note triage, and status synthesis — all through Claude Code's CLI.

Kit is a separate project from TodoTalk (the personal system). It shares architectural patterns (SQLite + MCP tools + Claude Code CLI) but is purpose-built for work: project tracking, stakeholder updates, deadline management, and coordinating across a team.

---

## Why This Exists

Brendan is a Tech Lead / IC at Thriveworks who inherited PM responsibilities when his PM (Diana) went out for 3-5 months starting March 2026. He now manages multiple projects, a team of developers, and produces stakeholder updates — on top of IC and tech lead work.

He needs:
- A brain dump system for work tasks, linked to specific projects (initiatives)
- Daily planning that starts from Google Calendar (meetings are the skeleton of work days)
- Meeting note triage — paste transcripts, file them in Obsidian, extract action items conversationally
- Status synthesis — pull together DB state, Obsidian notes, and GitHub repo activity into stakeholder updates
- Conversation continuity — Kit remembers what happened last session

He does NOT need:
- Personal life planning (that's TodoTalk Buddy)
- Identity tracking or XP (that's the personal system)
- Life coaching (that's Lux)
- Direct code writing (that's dev agents)

---

## Architecture Decisions

### 1. Hybrid Database + Obsidian

- **SQLite** for operational/structured data: brain dump items, initiatives, deadlines, daily plans, team roster, conversation continuity
- **Obsidian** for unstructured knowledge: meeting notes, project context docs, career goals
- The `initiatives` table bridges both — it has structured fields AND points to an Obsidian folder via `obsidian_folder`

### 2. Google Calendar Is the Event Source of Truth

Events are NOT stored in the database. Daily planning reads from Google Calendar MCP and merges with database tasks. When Kit plans a day:
1. Pull Google Calendar events for that date (via `gcal_list_events`)
2. Pull inbox items (scheduled for that date or unscheduled high-priority)
3. Merge into a daily plan stored in the `dailies` table (tasks only — events are referenced, not duplicated)

### 3. Kit Reaches Into the Thriveworks Repo

Kit stays in the BriefCase directory but has full access to the Thriveworks monorepo via `gh` CLI and `git` commands. It can check branches, list PRs, read recent commits, and connect repo activity to initiative status — all without running inside the Thriveworks repo.

### 4. Global Skills as a Bridge

Three global skills (`/thrive-status`, `/stakeholder-update`, `/project-retro`) are installed at `~/.claude/commands/` and available from any repo. They query Kit's database and vault directly via `sqlite3` CLI and file reads — no MCP server dependency. This lets a BMAD agent in the Thriveworks repo pull initiative context without Kit's MCP running.

### 5. Conversational Meeting Triage

When user pastes meeting notes, Kit:
1. Files them in Obsidian under the initiative's folder
2. Summarizes the content
3. Proposes actions: "Update the deadline? Brain dump a follow-up? Plan something for tomorrow?"
4. User decides what to act on

No silent automation. No auto-creating tasks. Always conversational.

### 6. Tools-First (Claude Code CLI Compatibility)

Use MCP tools, not resources. Resources don't work reliably in Claude Code CLI.

---

## Database Schema

```sql
CREATE TABLE inbox (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    complexity INTEGER DEFAULT 1,     -- 1-3 (1=simple, 2=moderate, 3=complex)
    urgency INTEGER DEFAULT 1,        -- 1-3 (1=someday, 2=this week, 3=ASAP)
    status TEXT DEFAULT 'capture',    -- capture, scheduled, completed
    initiative_id INTEGER,            -- FK to initiatives (nullable)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    printed_at TIMESTAMP,
    scheduled_at TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (initiative_id) REFERENCES initiatives(id)
);

CREATE TABLE initiatives (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'active',     -- active, paused, completed
    obsidian_folder TEXT,             -- "Projects/insurance-management"
    deadline DATE,
    tags TEXT,                        -- JSON array
    repo_path TEXT,                   -- Path to git repo
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE initiative_members (
    id INTEGER PRIMARY KEY,
    initiative_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    role TEXT,                        -- "Developer", "QA", "Stakeholder"
    FOREIGN KEY (initiative_id) REFERENCES initiatives(id)
);

CREATE TABLE dailies (
    id INTEGER PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    tasks TEXT NOT NULL,              -- JSON array of daily items
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE conversation_notes (
    id INTEGER PRIMARY KEY,
    summary TEXT,
    next_intentions TEXT,
    topics TEXT,                      -- JSON array
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## MCP Tools (12 — Phase 1)

| Tool | Purpose |
|------|---------|
| `brain_dump` | Capture a task to the inbox with optional initiative linkage |
| `get_capture_list` | Query inbox items, filter by initiative/status |
| `complete_task` | Mark an inbox item completed |
| `delete_task` | Permanently remove an inbox item |
| `manage_initiative` | CRUD for initiatives (create, update, get, list, archive) |
| `manage_initiative_members` | Add/remove/list team members on an initiative |
| `plan_daily` | Create or update a daily task plan (tasks only) |
| `query_daily` | Look up a specific day's plan |
| `get_forecast` | DB-side forecast: deadlines, high-priority items, current time |
| `get_recent_activity` | Recent dailies and conversation notes |
| `save_conversation_notes` | Save session context for continuity |
| `backup_database` | Timestamped backup (SQL copy + JSON export) |

---

## Implementation Phases

### Phase 1: Core Planning (Complete)
- Database with 5 tables
- 12 MCP tools for brain dumps, initiatives, daily planning, forecasting, system
- Kit agent instructions with activation checklist
- Setup script, config loader, user profile
- ThriveNotes vault restructured for Kit
- Global skills: `/thrive-status`, `/stakeholder-update`, `/project-retro`

### Phase 2: Meeting Intelligence (Planned)
- `obsidian.py` helper for vault read/write/search
- `file_meeting_notes` tool — file, summarize, propose actions
- `search_notes` tool — keyword search scoped to initiative/date
- `get_initiative_status` tool — full status with Obsidian + gh CLI

### Phase 3: Status & Reporting (Planned)
- `draft_status_update` tool — synthesize DB + Obsidian + gh into updates
- `project_retro` tool — week-by-week retrospective with trends

### Phase 4: Printing & Polish (Planned)
- `/print-daily` skill with thermal printer support
- Formatting: 12-hour time, checkboxes for tasks, no checkboxes for events
