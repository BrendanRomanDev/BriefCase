# BriefCase (Kit) — User Guide

A guide for anyone using or maintaining Kit, Brendan's work planning assistant.

---

## What Kit Does

Kit is an MCP-powered agent that helps manage work at Thriveworks through Claude Code. It handles:

- **Brain dumps** — quickly capture tasks with priority and project linkage
- **Initiative tracking** — manage projects, deadlines, and team members
- **Daily planning** — merge Google Calendar events with tasks into a daily plan
- **Meeting note triage** — paste notes, get summaries and proposed actions
- **Status synthesis** — pull together database, Obsidian notes, and GitHub activity
- **Session continuity** — Kit remembers what happened last time

---

## Getting Started

### Prerequisites

- Python 3.x with `mcp` and `pyyaml` packages
- Claude Code CLI
- Google Calendar MCP configured in Claude Code
- `gh` CLI installed and authenticated
- Obsidian vault at `~/Notes/ThriveNotes/`

### First-Time Setup

```bash
cd ~/Programming/BriefCase
bash scripts/setup.sh
```

This creates:
- `~/.briefcase/briefcase.db` — the SQLite database
- `~/.briefcase/backups/` — backup directory
- `~/.briefcase/user_profile.yaml` — your profile (edit this with real details)
- Obsidian vault directories under `~/Notes/ThriveNotes/Projects/`

### Edit Your User Profile

Open `~/.briefcase/user_profile.yaml` and fill in:
- `team_name` and `reports_to`
- Project descriptions and repo paths
- Team members and their roles
- Printer settings (if using thermal printing)

### Start Kit

From the BriefCase directory:
```
/kit
```

Kit runs through its activation checklist — pulls calendar events, checks deadlines, loads recent activity — then greets you with what's relevant today.

---

## Daily Workflow

### Morning: Plan Your Day

Start a `/kit` session. Kit pulls your calendar and surfaces what needs attention. Ask Kit to plan the day:

> "Plan tomorrow for me"

Kit merges calendar events with open tasks and proposes a daily plan. Adjust as needed — Kit saves the tasks to the database.

### Throughout the Day: Brain Dumps

Whenever a task comes to mind:

> "Brain dump: Review API contract changes for insurance management, urgency 3"

Kit captures it to the inbox, links it to the initiative, and moves on. No friction.

### After Meetings: Triage Notes

Paste meeting notes or Gemini transcripts directly into a Kit session:

> "Here are notes from the insurance standup: [paste]"

Kit summarizes, proposes actions, and lets you decide what to capture as tasks, what to update, and what to skip.

### End of Day: Save Context

Kit saves conversation notes automatically when you end a session. These carry context into your next session — what you discussed, what to pick up next.

---

## Key Concepts

### Inbox Items

Tasks live in the inbox with two dimensions:
- **Complexity** (1-3): 1=simple, 2=moderate, 3=complex
- **Urgency** (1-3): 1=someday, 2=this week, 3=ASAP

Items can optionally link to an initiative. Kit uses these ratings to surface what matters in forecasts — it won't nag you about low-priority items.

### Initiatives

Projects/workstreams with:
- Name, slug, description, status, deadline
- Team members with roles
- Link to an Obsidian folder (`Projects/{slug}/`)
- Link to a git repo (for `gh` CLI integration)

### Dailies

A daily plan is a date + a JSON array of tasks. Events are NOT stored — they come from Google Calendar at runtime. This prevents data duplication and keeps Google Calendar as the single source of truth for scheduling.

### Conversation Notes

Session summaries with next intentions and topics. Kit reads the last few days of notes at startup to maintain continuity across sessions.

---

## Where Data Lives

| Data | Location | Managed By |
|------|----------|-----------|
| Tasks, initiatives, dailies, session notes | `~/.briefcase/briefcase.db` | Kit MCP tools |
| Meeting notes, project docs | `~/Notes/ThriveNotes/Projects/` | Kit + Obsidian |
| Calendar events | Google Calendar | Google Calendar MCP |
| Repo activity (PRs, commits) | Thriveworks repo | `gh` CLI (read-only) |
| User profile, preferences | `~/.briefcase/user_profile.yaml` | Manual edit |
| Backups | `~/.briefcase/backups/` | `backup_database` tool |

### ThriveNotes Vault Structure

```
~/Notes/ThriveNotes/
├── Projects/                # Kit-managed, per-initiative
│   ├── insurance-management/
│   │   ├── README.md        # Living status doc
│   │   └── meetings/        # YYYY-MM-DD-title.md
│   ├── symplr/
│   ├── credit-card-validation/
│   └── ocr-patient-upload/
├── Meetings/general/        # Meetings not tied to an initiative
├── Career/                  # Professional goals, 1:1 notes
├── Dailies/                 # Optional daily plan archive
├── assets/                  # Attachments, images
├── templates/               # Obsidian templates
└── legacy/                  # Pre-Kit notes (read-only reference)
```

---

## Global Skills

These work from any repo — no MCP server needed. They query the database and vault directly.

### `/thrive-status [slug]`

Full status report for an initiative: DB state, meeting notes, repo activity, open items, team.

### `/stakeholder-update [slug]`

Drafts a professional stakeholder communication. Presents a draft for review before sending.

### `/project-retro [slug] [weeks]`

Week-by-week retrospective: meeting notes, completed tasks, repo activity, trends. Default 4 weeks.

---

## Backups

Kit can create timestamped backups (both `.db` copy and `.json` export):

> "Back up the database"

Backups go to `~/.briefcase/backups/`. Run backups before major changes or periodically for safety.

---

## Troubleshooting

**Kit MCP tools not available:** Make sure you're in the BriefCase directory and the `.mcp.json` is configured. Restart Claude Code if needed.

**Database not found:** Run `bash scripts/setup.sh` to initialize.

**Calendar events not showing:** Google Calendar MCP must be configured separately in Claude Code settings. Kit doesn't manage this.

**gh CLI errors:** Run `gh auth status` to verify authentication.

---

## Feature Enhancements

Track planned improvements and ideas here as they come up.

### Planned (Phase 2-4)

- [ ] `file_meeting_notes` — auto-file pasted notes to Obsidian with frontmatter
- [ ] `search_notes` — keyword search across the vault, scoped by initiative/date
- [ ] `get_initiative_status` — unified status pulling all three data sources
- [ ] `draft_status_update` — MCP tool version of `/stakeholder-update`
- [ ] `project_retro` — MCP tool version of `/project-retro`
- [ ] `/print-daily` — thermal printer integration for daily checklists
- [ ] Obsidian helper module (`obsidian.py`) for vault read/write/search

### Ideas / Wishlist

_Add ideas here as they come up during real usage._
