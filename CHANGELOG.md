# BriefCase Changelog

## Packaging follow-ups — 2026-05-16

- **`scripts/health-check.sh`** — doctor script that reports the status of every component (venv, dependencies, DB integrity, MCP registration, sidecar, token, launchd) in one pass. First stop when something looks off. Wired into the troubleshooting sections of `README.md` and `docs/INSTALL.md`.
- **Published to GitHub** as `BrendanRomanDev/BriefCase` (private). Origin remote now wired so `git clone` is the entry point on new machines.
- **Dotfiles `setup/05-briefcase.sh`** (sibling change) — clones BriefCase to `~/Programming/BriefCase` (creating `~/Programming` if absent) and runs its `./setup.sh`. Completes the dotfiles → BriefCase install loop so a fresh mac gets the whole stack from `setup/00–05`.

## Packaging — 2026-05-16

Repo is now installable on a fresh machine via a single idempotent script. Modelled after the peon-ping dotfiles flow ([install] / [skip] / [ok] / [warn] echoes), and designed to be invokable from a future `~/.dotfiles/setup/05-briefcase.sh`.

### `setup.sh` (repo root)

One command brings up a fresh work mac. Six phases, each idempotent:

| Phase | Action |
|---|---|
| 0 | Preflight — verifies `python3` and `claude` are on PATH. |
| 1 | Creates `venv/`, installs `requirements.txt`. |
| 2 | Creates `~/.briefcase/{backups,logs}`, initialises `briefcase.db`, writes a `user_profile.yaml` template if one isn't already there. |
| 3 | Registers the MCP server with Claude Code at **user scope** (so `/kit` works from any working directory). Idempotent — skips if already registered. |
| 4 | Delegates to `briefcase/sidecar/install.sh`, which installs the launchd plist and starts the sidecar. |
| 5 | Prints next steps + the sidecar auth token. |

The old `scripts/setup.sh` is now a thin shim that forwards to the new root script (preserves muscle memory).

### Database backup + restore

The DB at `~/.briefcase/briefcase.db` is the only thing that doesn't reconstitute itself from the repo. Two new scripts make it easy to back up and move:

- **`scripts/backup-db.sh`** — uses SQLite's online backup API (safe under concurrent writes from the sidecar / MCP server). Writes to `~/.briefcase/backups/briefcase_<stamp>.db` and *also* mirrors to `~/Library/Mobile Documents/com~apple~CloudDocs/BriefCase-Backups/` if iCloud Drive is on. `--local` skips the iCloud mirror.
- **`scripts/restore-db.sh`** — interactive picker, `--latest` (newest by mtime across both locations), or explicit path. Verifies integrity before touching the live DB. Takes a safety pre-restore snapshot of the current DB so the restore is itself reversible.

The recommended off-machine durability story is the iCloud Drive mirror — no extra tooling, no second repo, no separate cloud account. On a fresh mac you log in, iCloud syncs the mirror down, run `scripts/restore-db.sh --latest`, done.

### Documentation

- **`README.md`** (new, repo root) — quick-start, architecture diagram, what-lives-where, troubleshooting.
- **`docs/INSTALL.md`** (new) — long-form new-machine walkthrough: prerequisites → clone → setup → profile → extension → token → restore → verify.
- **`docs/user-guide.md`** updated to reference the new top-level setup path.

### `.gitignore` hardening

Defensive ignores added for `sidecar_token`, `user_profile.yaml`, `last_draft.txt`, and `.briefcase/` — none of those should ever land in repo tracking, but explicit beats lucky.

### Cross-repo sync (dotfiles)

Sibling work in `~/.dotfiles/`:
- `bin/sync` — runs `git pull` + `./setup.sh` in every repo listed in `repos.conf`. Currently registers BriefCase.
- `bin/wip-status` — silent-when-clean drift reporter wired into shell startup. Reports ahead/behind/dirty per managed repo.

The pair turns "make this machine current" into one command and "what's stale" into a passive shell-startup notice.

## v0.9.0 — 2026-04-29 / 2026-04-30

Session arc: Chrome extension grew a richer capture vocabulary (flags), Kit learned to act on those flags during triage, the sidecar gained a draft endpoint backed by the user's Claude Code subscription, and a per-initiative decision log landed for cross-repo workflows.

### Capture-time flags (extension compose popup → triage_queue → Kit triage flow)

The compose popup gained a checkbox grid that lets Brendan signal *what kind of work* a capture represents at the moment of capture, so Kit can act on those signals during triage instead of inferring from content alone.

**Schema:** new `flags` JSON column on `triage_queue` (additive migration). Each capture POSTs an optional `flags` dict via the sidecar. Kit reads the dict during triage and adapts behavior.

**Flag set:**

| Flag | UI label | Behavior |
|---|---|---|
| `is_brain_dump` | Brain dump (postpone for later) | Pre-decides destination → triage skips the "what should I do with this?" question and goes straight to brain_dump field collection. |
| `needs_jira` | Jira ticket | After triage, propose drafting a ticket. If `epic_hint` also set, propose that as parent. Drafts via the atlassian MCP if loaded; falls back to paste-ready body otherwise. Records new ticket via `add_external_ref` on the resulting entity. |
| `needs_code_review` | Code review / repo context | After triage, tag the resulting inbox/initiative with `needs_code_context`. Future Thriveworks-repo CC sessions query `get_capture_list(tags=['needs_code_context'])` to find work needing dev attention. |
| `search_around` | Search around (vault + inbox) | BEFORE proposing destinations, run `search_notes` + `get_capture_list` for related context. Kit surfaces what it found so Brendan has context for the decision. |
| `needs_calendar` | Calendar follow-up | After triage, propose a calendar event via the gcal MCP. (Loose semantic; rename to `needs_meeting` with attendees flow is queued.) |
| `needs_reply` | This will need a reply | Tag the resulting inbox item with `needs_reply` so future triage walks surface it for drafting. Or draft inline now (read voice profile, draft, present, optionally pbcopy). |
| `is_decision` | Decision (file under an initiative) | Synthesize the captured content into a structured decision (one-liner + rationale + decided_at) and call `record_decision` to file under an initiative's decision log. See Decision log section below. |
| `epic_hint` | (text input, conditional on Jira flag) | Free-text Jira epic key. When `needs_jira` is checked, this input appears for Brendan to type the parent epic. |

**Auto-derivation:** `triage_item` now passes `tags=['needs_code_context']` through to `brain_dump` (and to `manage_initiative` via `tags_mode='append'` for the initiative path) when the queue item's `flags.needs_code_review` is true. Caller-supplied tags merge with the auto-derived ones.

**Order of operations in triage:** `search_around` (informs the rest) → triage destination (driven by `is_brain_dump` if set, else user choice) → post-resolution side-effects (`needs_jira` / `needs_code_review` / `needs_calendar` / `needs_reply` / `is_decision`).

### Decision log (per-initiative, status='pending'/'consumed')

Brendan can now capture decisions throughout the day and have them file under specific initiatives, ready for downstream consumption — typically a Thriveworks-repo dev session that updates an in-repo `decisions.md` on a feature branch.

**Schema:** new `decision_log` table with `initiative_id`, `decision`, `rationale`, `decided_at` (ISO date), `source_url`, `metadata`, `status`, `consumed_at`, `created_at`.

**Three MCP tools (all available from any cwd since briefcase is user-level):**

- `record_decision(decision, initiative_slug | initiative_id, rationale?, decided_at?, source_url?, metadata?)` — Kit calls during triage when `is_decision` is set. Defaults `decided_at` to today UTC if not supplied; pulls from chat metadata timestamps when available.
- `get_decision_log(initiative_slug?, initiative_id?, status='pending')` — query. Default 'pending' (use 'consumed' or 'all' for history). Each row carries decision, rationale, decided_at, source_url, metadata.
- `consume_decisions(initiative_slug? | initiative_id? | decision_ids?)` — flip rows to status='consumed' after they've been filed downstream. Keeps history with `consumed_at`.

**Workflow:**

1. Capture: highlight chat conversation → BriefCase compose popup → check **Decision** + mention initiative in additional context → Send.
2. Triage: Kit determines the initiative (asks if unclear), synthesizes decision + rationale + decided_at, confirms, calls `record_decision`. Resolves the queue item as `mark_resolved` (or alongside `brain_dump` if follow-up work is implied).
3. Consume: in the Thriveworks repo on a feature branch, ask the dev agent: *"check briefcase decisions for insurance-management and update decisions.md."* Dev agent calls `get_decision_log(slug=...)`, reads existing `decisions.md`, appends in its convention, calls `consume_decisions(slug=...)` to mark filed.

**Critical rule:** BriefCase NEVER writes to in-repo files. The dev agent on each branch owns `decisions.md`; BriefCase only provides the structured data via MCP.

### Draft assistant (sidecar `/draft` + extension "Draft now" button + `/draft` skill polish)

Three layers added so Brendan can produce voice-correct chat replies without leaving the browser or polluting his clipboard with terminal-wrap artifacts.

**Sidecar `POST /draft`:**
- Inputs: `content` (the message being replied to), `context` (Brendan's notes/intent), `tone` (`informal`|`formal`), `mode` (`reply`|`new`|`cleanup`).
- Reads `~/.claude/rules/brendan-voice-profile.md` and inlines it into the prompt as system-prompt material.
- Spawns `claude -p` as a subprocess (resolves binary via `shutil.which` then known fallback paths). Uses Brendan's existing Claude Code subscription auth — no separate API key.
- Captures stdout, returns `{status, draft, elapsed_ms}`. Persists draft to `~/.briefcase/last_draft.txt` so the `recopy` shell function can restore it later.
- 60s timeout. Auth via the same `X-BriefCase-Token` as `/clip`.
- launchd plist PATH widened to include `~/.local/bin` so `claude` is reachable from the sidecar's daemon context.

**Extension compose popup "Draft now (⌘D)" button:**
- Always-visible (sits next to Send). Calls sidecar `/draft` via the service worker, takes ~5-15s.
- On result, an editable textarea appears below the action row with the drafted reply, plus **Copy to clipboard** / **Re-draft** / **Hide** buttons.
- Distinct from the **"This will need a reply"** checkbox (which is for *deferred* drafting via Kit at triage time). Button = immediate-now; checkbox = persistent-tag-for-later.

**`/draft` skill update (~/.claude/commands/draft.md):**
- After presenting the drafted message, the skill now ALWAYS pipes the body through `pbcopy` AND writes to `~/.briefcase/last_draft.txt` via `tee` heredoc. Single step, both clipboard and persistence.
- Heredoc uses a quoted delimiter (`'BRIEFCASE_DRAFT_EOF'`) so backticks/`$`/etc inside the draft are not interpolated.
- Copies ONLY the drafted body — no `**Mode:**` header, no divider, no markdown wrappers.

**`recopy` shell function (in `~/.zshrc`):**
- `recopy` from any terminal restores `~/.briefcase/last_draft.txt` to clipboard.
- File is overwritten (not appended) on every new `/draft`, so size stays bounded.

### Extension theme system + UI fixes

13 curated themes selectable via the options page. Compose popup, options page, and toolbar popup all theme-aware.

- **Themes (13):** Light, Dark, System (follow OS via `prefers-color-scheme`), Sepia, Solarized Light, Solarized Dark, Nord, Dracula, Gruvbox Dark, Tokyo Night, Catppuccin Latte, Catppuccin Mocha, High Contrast.
- **`themes.css`** defines all themes as `[data-theme="..."]` CSS variable sets.
- **`theme.js`** reads canonical theme from `chrome.storage.sync` backed by synchronous `localStorage` cache (prevents flash-of-unstyled-content on popup open). Applies via `data-theme` attribute on `<html>`. Listens for cross-page changes via `chrome.storage.onChanged`.
- **Options page** has a Theme section with a dropdown + 4-color live swatches showing `--bg`, `--pane`, `--ink`, `--accent`. Change instantly applies across all extension pages.

**Cancel button contrast bug:** previous build used `background: #e2e8f0` hardcoded on the cancel button → produced white-on-light-gray on Nord/Dracula/Gruvbox/Tokyo Night/etc. Replaced with `background: var(--pane)` + `color: var(--ink)` + `border: 1px solid var(--border)`. Send button changed `color: white` → `color: var(--bg)` so dark themes invert cleanly. Audited all 13 themes for ≥3.0 contrast on both buttons; passes.

**Checkbox layout fix:** the global `label { justify-content: space-between }` rule was leaking into the `.flag-row` checkboxes, putting the checkbox on the LEFT and label on the RIGHT of each grid cell (visually confusing — looked like the box belonged to the next column's label). Scoped that rule to `.field-label` so flag rows now use `flex-start` and pack `[ ] Label` tightly.

**Compose popup window dimensions:** 660 × 730 (started at 640 × 620, dialed in over a few iterations).

**Single-level context menu:** removed the nested "BriefCase → Send to BriefCase..." submenu in favor of a single top-level **"Send to BriefCase..."** item.

**Keyboard shortcut:** `commands.open_compose` declared in manifest with `Ctrl+Shift+Y` / `⌘⇧Y` suggestion. User must set it themselves at `chrome://extensions/shortcuts` (Chrome doesn't auto-bind). Service worker reads the active tab's selection via `chrome.scripting.executeScript` and opens the compose popup. Bypasses pages like Google Docs that hijack right-click.

**`clipboardRead` permission** so the compose popup can auto-fill the source URL from clipboard on open (the "Copy message link" → right-click flow on Google Chat).

### External refs (Jira / Confluence / Figma / etc. linkage)

Added 2026-04-24 (covered briefly here for completeness; see commit `e8bb70b` for full landing).

- New `external_refs` table: `(entity_type, entity_id, ref_type, ref_key, ref_url, label, created_at)` with indexes on `(entity_type, entity_id)` and `ref_key`.
- Three MCP tools: `add_external_ref`, `remove_external_ref`, `list_external_refs` (filter by entity, ref_type, or `ref_key` for reverse lookup).
- `briefcase/mcp_server/refs.py` auto-derives canonical URLs for `jira_epic` / `jira_ticket` ref types from `settings.yaml` `integrations.jira.base_url`.
- `settings.yaml` gained `integrations.jira.base_url: https://thriveworks.atlassian.net`.

### `kit-lite` skill (~/.claude/commands/kit-lite.md)

A leaner Kit variant for non-planning sessions. Same persona, same MCP, same capabilities — but no front-loaded activation context (no gcal, no forecast, no rollup, no recent activity, no PDLC list). One cheap call on startup: `get_triage_queue` for the count, mentioned in the greeting only if non-empty.

Use cases:
- Quick brain dump from any cwd without paying full Kit's startup cost
- Triage walk in a Thriveworks-repo cwd where code-context tools are scoped naturally
- Code research targeting items tagged `needs_code_context`
- Drafting / quick captures / decision filing without the full briefing

Full Kit (`/kit`) remains for daily planning, Monday briefings, end-of-week reviews — anywhere the front-loaded context is the point.

### `manage_initiative.tags_mode` fix

Updating `tags` previously overwrote the existing list. Default now is `tags_mode='append'` (merges + dedupes). Explicit `tags_mode='replace'` or `'remove'` available for other ops.

### Configuration knobs (settings.yaml)

```yaml
sidecar:
  port: 8989

integrations:
  jira:
    base_url: https://thriveworks.atlassian.net
```

### Files Changed (this session)

- DB: `briefcase/mcp_server/database.py` (flags column on triage_queue, tags column on inbox, external_refs table, decision_log table, helpers, migrations)
- New tools: `add_external_ref.py`, `list_external_refs.py`, `remove_external_ref.py`, `record_decision.py`, `get_decision_log.py`, `consume_decisions.py`
- New helpers: `briefcase/mcp_server/refs.py`
- Modified tools: `brain_dump.py`, `get_capture_list.py` (tags filter), `manage_initiative.py` (tags_mode + obsidian helper extraction), `triage_item.py` (auto-derive tags from flags)
- Sidecar: `briefcase/sidecar/server.py` (accept flags on /clip, new /draft endpoint with claude -p), launchd plist template (PATH widened)
- Extension: full revamp under `extension/` — `themes.css`, `theme.js`, `compose.html`/`compose.js` (checkboxes + draft button + URL editable + clipboard detect), `options.html`/`options.js` (theme selector), `popup.html` (theme integration), `background.js` (single menu, hotkey, DRAFT_REPLY handler), `manifest.json` (commands + clipboardRead), `README.md`
- Skills: `~/.claude/commands/draft.md` (pbcopy + persistence), `~/.claude/commands/kit-lite.md` (NEW lean Kit variant), `~/.claude/commands/kit.md` (capture-time flags handling, decision log section, kit-lite reference)
- Server instructions: `briefcase/mcp_server/server.py` (SERVER_INSTRUCTIONS updated for flags handling, decision log, capture-time flag protocol)
- Shell: `~/.zshrc` (`recopy` function)

---

## v0.5.0 — 2026-04-01

### Weekly Planning Layer

Two new capabilities that give Kit week-level awareness between loose brain dumps and day-specific dailies.

**target_week on inbox items**
- New `target_week` column on `inbox` table (ISO week format, e.g. `2026-W15`)
- `brain_dump` accepts optional `target_week` param — use when an item should happen in a specific week but doesn't have an exact day
- `get_forecast` now includes `targeted_this_window` — inbox items whose target week falls within the forecast window
- `get_capture_list` supports `target_week` filter
- DB migration is additive (ALTER TABLE ADD COLUMN) — no data loss, existing rows get NULL

**weekly_rollup tool**
- New MCP tool: `weekly_rollup(target_week?, lookahead_weeks=2)`
- Gathers from DB: dailies, conversation notes, inbox items created/completed in the target week
- Gathers from Obsidian: meeting notes filed that week (scans `Projects/*/meetings/` and `Meetings/general/` by date prefix)
- Gathers look-ahead: target_week items for upcoming weeks + approaching initiative deadlines
- Writes rollup to `ThriveNotes/weeklies/{iso-week}-rollup.md`
- Sections: Meetings & Decisions, Work Completed, Open Threads, Look Ahead, Session Context

**Kit agent updates**
- Activation checklist now includes: check for current week's rollup, generate if missing (Monday/Tuesday)
- Greeting includes targeted items for the current week and rollup context
- Brain dump triage now has three options: loose capture, target a week, or slot into a day
- SERVER_INSTRUCTIONS and kit.md updated in sync

### Files Changed
- `briefcase/mcp_server/database.py` — schema, migration, CRUD for target_week
- `briefcase/mcp_server/tools/brain_dump.py` — target_week param
- `briefcase/mcp_server/tools/get_forecast.py` — targeted_this_window section
- `briefcase/mcp_server/tools/get_capture_list.py` — target_week filter
- `briefcase/mcp_server/tools/weekly_rollup.py` — new tool
- `briefcase/mcp_server/server.py` — v0.5.0, tool registration, SERVER_INSTRUCTIONS
- `.claude/commands/kit.md` — activation checklist, triage logic, rollup section

---

## v0.4.0 — 2026-03-28

Phase 4: HTML receipt printing pipeline with thermal printer support. `print_daily_list` and `print_custom` tools. Webdriver-manager for auto Chrome version matching.

## v0.3.0 — 2026-03-27

Phase 3: Status & Reporting. `draft_status_update`, `project_retro` tools. Week-by-week retrospective with velocity trends.

## v0.2.0 — 2026-03-26

Phase 2: Meeting intelligence. `file_meeting_notes`, `search_notes`, `get_initiative_status` tools. Obsidian vault integration.

## v0.1.0 — 2026-03-25

Initial release. Core inbox, initiatives, dailies, conversation notes. `brain_dump`, `plan_daily`, `get_forecast`, `get_recent_activity`, `get_capture_list`, `complete_task`, `delete_task`, `manage_initiative`, `manage_initiative_members`, `query_daily`, `save_conversation_notes`, `backup_database`.
