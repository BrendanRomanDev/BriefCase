# BriefCase Changelog

## Self-maintaining briefing doc — 2026-07-08

New `render_briefing` tool (server bumped to `0.14.0`) that maintains Brendan's pen-and-paper daily carry-over list as a self-updating document at `~/Notes/ThriveNotes/briefing.md`, symlinked to `~/Desktop/Briefing.md`.

### What it is (and deliberately is NOT)

The briefing is a **co-authored working surface, NOT a projection of the database**. It's *informed by* the DB but allowed to lead it — it holds pre-initiative scoping threads, gear tickets, open-loop "what's the status of X" items, and don't-forget items (open enrollment deadline, broken Storybook deploy, OCR vendor drop). The DB is frequently behind; that's expected. Maintaining the briefing is the ritual that keeps Kit's data model honest, not the other way around.

### Reconciliation flow (read-merge-reconcile, never regenerate)

1. `render_briefing(mode='read')` — gather step. Returns the existing doc verbatim, a DB snapshot (initiatives + external_refs w/ new `assignee`/`status_line` + members + pending decisions + orphan ticket refs + roster), a batched `mismatches` report, and profile buckets. Returns a `scaffold` when no doc exists yet.
2. Agent treats Brendan's prose as durable truth, layers in what changed, and surfaces `mismatches` as ONE "DB looks out of date — sync any?" checklist. DB corrections happen via the normal tools (`manage_initiative` / `add_external_ref` / `update_external_ref` / `manage_initiative_members`) based on his picks. The doc write NEVER blocks on DB sync.
3. `render_briefing(mode='write', content=...)` — commit step. Writes the approved merged markdown, stamps a meta footer (idempotent — doesn't stack on re-render), and ensures the Desktop symlink. This tool NEVER mutates the DB.

### Doc shape

Grouped by bucket/theme (same buckets as `user_profile.yaml` projects), plus **Watch / Don't Forget** and **Backlog / Scoping** zones. Each line is one open loop: **item · owner · open-loop-or-status · link(s)**. Owner optional (`unassigned`); status is usually a question/next-action, not a closed fact.

### Schema + tool changes

- `external_refs` gains `assignee` and `status_line` columns (migrated via the existing `_migrate()` ALTER pattern). A Jira ticket ref now carries its own owner + one-line status.
- New `update_external_ref` tool — set assignee/status_line/label/ref_url on an existing ref without re-adding it. Empty string clears a field (e.g. un-assign).
- `add_external_ref` extended with optional `assignee` / `status_line`.

### Triggers + queue-walk integration

Rendered on explicit ask; offered once after Jira/ref changes in a session; offered once at the end of a queue-walk. NOT on every activation — but full-Kit activation now *reads* `briefing.md` (cheap file read) so Kit knows Brendan's open loops when planning. During triage, items that relate to an existing briefing line/bucket can be folded in (source link + one-line update), per-item with Brendan's confirmation.

### Self-maintaining transcript sync (presence-triggered)

The briefing keeps itself current by folding in the day's **recorded meetings** — without a cron and without metered API cost. The key realization: a cloud routine can't reach the local DB/vault, and any *unattended* inference (sidecar + `claude -p`) bills as API tokens. So the sync **piggybacks on Brendan already being in a Kit/kit-lite session** (subscription-covered) rather than firing on a clock.

- **Source:** Google Calendar. A recorded meeting carries a "Notes by Gemini" Google Doc in its `attachments`; that's the transcript. No such attachment → logged as *not recorded*, never fabricated.
- **`briefing_sync_state` tool** — freshness marker (`~/.briefcase/briefing_sync_state.json`) + weekend-aware day-window logic (`briefcase/mcp_server/sync_state.py`). `action='get'` returns `is_stale` + `scan_dates`; `action='record'` marks a sync done. "Everything since the last sync," so a **Monday reaches back to Friday** (Brendan doesn't work weekends); a gap spanning a weekend picks up Thu+Fri+Mon; first run defaults to a small window, not all history; explicit dates override.
- **Presence-triggered dispatch:** on Kit/kit-lite activation, if the sync is stale it's dispatched **silently** to a sub-agent — a WezTerm tangent tab when available (via `get_runtime_capabilities()`), else an in-session `Agent`. Out-of-band so the main conversation stays fast. The sub-agent's instructions live at `.claude/commands/sync-transcripts.md` (symlinked to `~/.claude/commands/` via `command-bindings.conf`, invocable as `/sync-transcripts`).
- **Staged, never live:** the sub-agent writes DB changes live but the briefing only to `briefing.staged.md` (new `render_briefing` `mode='staged'`), leaving a `<!-- sync-log -->` block. Brendan's Desktop `Briefing.md` never changes under him.
- **"catch me up" / "briefing":** reviews the staged proposal + sync log, then `render_briefing(mode='promote')` moves staged → live on approval.

### render_briefing modes

Grew from two modes to four: `read` / `write` / `staged` (proposal, no symlink) / `promote` (staged → live, clears staged). The meta footer is idempotent across re-renders and promotions.

Triple instruction sync updated: `.claude/commands/kit.md`, `briefcase/mcp_server/server.py` (SERVER_INSTRUCTIONS + activation checklist + TRANSCRIPT SYNC section), `~/.dotfiles/claude/commands-work/kit-lite.md`. New `/sync-transcripts` sub-agent command + `command-bindings.conf` entry.

## Side panel migration + concurrent auto-sweep — 2026-06-03

Three threads of work landed today under the `briefcase-capture-ux` initiative (see `~/Notes/ThriveNotes/Projects/briefcase-capture-ux/plan.md` for the full plan).

### Concurrent auto-sweep for the triage queue (commit `1fdc810`)

Kit's triage-walk auto-sweep is now a three-phase concurrent batch instead of one-item-at-a-time:

1. **Claim all** auto-flagged items in parallel (single assistant turn, N parallel `claim_triage_item` calls).
2. **Dispatch all** in parallel — Skill calls when tangent runtime is available, inline filing otherwise.
3. **Resolve all** in parallel via `triage_item(action='mark_resolved', ...)`.

Non-auto items drop into the interactive walk only AFTER the sweep finishes. Race handling: `already_claimed` drops that item from the rest of the sweep; mid-batch classify-failure releases the claim and demotes the item into the non-auto interactive bucket.

**Kudos carve-out reverted.** Earlier scaffolding had kudos always pausing for approval even when `auto_file=true` was set. That carve-out is gone — auto now means auto. If a kudos item is auto-flagged and tangent is available, the sweep dispatches it to a tangent like any other auto item; the tangent conversation IS the review surface, no second gate needed.

Triple instruction sync updated: `.claude/commands/kit.md`, `briefcase/mcp_server/server.py` (SERVER_INSTRUCTIONS), `~/.dotfiles/claude/commands-work/kit-lite.md`.

### Chrome extension: popup → side panel (commit `ce5a118` + follow-up polish)

Both surfaces — the action popup AND the free-floating compose window — collapsed into a single Manifest V3 side panel.

**What changed:**
- Manifest gets `sidePanel` permission, `side_panel.default_path: "sidepanel.html"`, and drops `action.default_popup`. Version bumped to `0.14.0`.
- `chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true })` registered in both `onInstalled` and `onStartup` so the toolbar icon opens the panel directly.
- Right-click "Send to BriefCase..." and `Cmd+Shift+Y` both call `chrome.sidePanel.open()` synchronously to preserve the user-gesture token, THEN run the async selection-capture chain. Without the sync-first ordering, Chrome silently drops the open call.
- Hydrate flow: panel reads `chrome.storage.session.pendingCapture` on load and clears it after consumption so tab-switches don't re-hydrate stale data. A `chrome.storage.onChanged` listener handles the "panel already open when a fresh capture arrives" case.

**Deletions:**
- `popup.html`, `popup.js` — the action popup was a 30-line health widget plus an unintentional Kudos button. The Kudos button was an artifact, never deliberate; dropping it entirely (no migration into the new surface). Health widget ported into the panel header.
- `compose.html` — the renderer-side compose form lives in `sidepanel.html` now.
- `openComposeWindow`, `openKudosCompose`, the `OPEN_KUDOS_COMPOSE` message handler, and every `chrome.windows.create` call from `background.js`.

### Side panel polish (uncommitted in this commit)

Several iteration passes on top of the bare migration:

- **Sticky action footer.** `Send / Draft now / Clear` are now anchored to the bottom of the panel in a `<footer class="sticky-footer">` with `position: sticky; bottom: 0`. The form body scrolls behind them so the buttons are always reachable even on long captures.
- **Header redesign.** The header is now `[favicon] [tab title] [health dot] [options]` in a single row. The old standalone `#health` div and `.source-title-block` are gone. The tab title replaces the static "BriefCase" brand text when there's a pending capture; falls back to "BriefCase" in the empty state. Long titles ellipsis-truncate with a `title=""` tooltip for the full string.
- **Health dot.** Sidecar status is a small colored dot (green = ok, red = err, muted = checking) next to the options link. Hover reveals `Sidecar 0.3.0 · 1 pending` (or `Can't reach sidecar · <error>`). Replaces the full-width health bar.
- **Favicon fallback.** When the captured tab has no resolvable favicon (S2 lookup fails or there's no pending capture at all), the BriefCase extension icon (`icons/icon-16.png`) shows in its place. The HTML ships with the fallback as the initial `src` so there's no broken-image flash on first paint. An `error` listener on the `<img>` swaps to the fallback if a real favicon URL fails to load at runtime.
- **Close hotkey.** New `Cmd+Shift+U` command bound to `chrome.sidePanel.close()`. Open (`Cmd+Shift+Y`) and close are two separate hotkeys rather than one toggling key — simpler than detecting open-state across tabs and avoiding edge cases around per-tab channeling. Chrome may require manual binding at `chrome://extensions/shortcuts` after the reload.
- **Esc semantics.** In the old free-floating window, Esc closed the window. In the persistent panel, Esc only blurs focus.

### Initiative tracking

Filed `briefcase-capture-ux` (initiative #31) with the full three-thread plan saved to `~/Notes/ThriveNotes/Projects/briefcase-capture-ux/plan.md`. T1 (auto-sweep) shipped; T2 (side panel) shipped + verified in Chrome; T3 (clipboard image capture into the panel) not started.

## Kudos action + draft-skill destination formatting — 2026-05-26

New end-to-end kudos drafting flow, plus a draft-skill formatting fix that resolves a long-standing Google Chat paste pain point.

### Draft skill (`~/.dotfiles/claude/commands-shared/draft.md`)

Added a **"Destination Formatting"** section. Voice mode (informal/formal) is now independent from destination (`markdown` / `google-chat` / `slack` / `plaintext`):

- `markdown` (default) — full Github-flavored markdown.
- `google-chat` — NO `*bold*`, NO `_italic_`, NO `[text](url)` link syntax. Bare URLs only. Chat doesn't render markdown, so any formatting char pastes as literal noise that Brendan has to clean up by hand.
- `slack` — treat like google-chat (Slack has its own mrkdwn dialect, but Brendan doesn't lean on it).
- `plaintext` — no formatting chars at all, no bullets.

The sidecar `/draft` endpoint accepts a new `destination` field (defaults to `google-chat` because that's the dominant extension use case) and injects the destination rules into the prompt. The extension's "Draft now" button passes `destination: "google-chat"` explicitly.

### Kudos capture path

- **Extension popup** now has a dedicated **Kudos** button. Clicking it opens the compose window in kudos mode: kudos banner instead of page-source block, recipient field surfaced, content + context textareas relabeled for kudos prompts, `flags.kudos = true` pre-set.
- **Compose form** also got a `flags.kudos` checkbox in the "What is this?" section so existing captures (e.g. a chat message you want to shout out) can be flagged for kudos drafting on the fly. The recipient field reveals when the checkbox is on; the optional `flags.kudos_recipient` rides along with the capture.
- **Wire format:** existing `/clip` endpoint, no schema changes. `kudos` and `kudos_recipient` are flags like any other.

### Kudos triage destination

`triage_item` now accepts `action='kudos'`. Like `thrivenote`, the agent owns the file write — Kit drafts in Brendan's voice with destination=google-chat, gets approval, appends to `~/Notes/ThriveNotes/kudos/YYYY-kudos.md` (creates folder + year file if missing, read-then-append), pbcopies, then calls `triage_item(action='kudos', resolution_note='<recipient> → <path>')` to close the queue item.

Entry format:
```
## YYYY-MM-DD — <Recipient>

<approved draft body>

_Context:_ <one-line summary of what triggered it>
```

### Auto-sweep carveout for kudos

Even when `auto_file: true` is set, kudos items do NOT silently file. The sweep drafts the kudos and stages it; Kit pauses for Brendan's approval before appending to ThriveNotes + pbcopying. Tone matters too much to file a shout-out silently. Documented in all three instruction surfaces (kit.md, kit-lite.md, SERVER_INSTRUCTIONS).

### Triple instruction sync

Updated all three Kit instruction surfaces with the `kudos: true` flag handler, the `kudos` triage destination, and the auto-sweep carveout: `.claude/commands/kit.md`, `~/.dotfiles/claude/commands-work/kit-lite.md`, and `SERVER_INSTRUCTIONS` in `briefcase/mcp_server/server.py`.

## Capture form redesign + attach threading + auto-run tangent dispatch — 2026-05-25

Three intertwined improvements to the capture → triage → action flow.

### Capture form (Chrome extension `compose.html`)

The flat 10-checkbox grid is gone. Flags now group by what they actually mean to Kit:

- **What is this?** — `is_brain_dump`, `is_decision`, `is_person`
- **Context to gather** — `needs_code_research`, `search_around`, `needs_web_research` (new)
- **Actions Kit takes** — `needs_jira`, `needs_pr_review`, `needs_meeting`, `needs_reply`
- **How Kit handles this** (visually set apart with a dashed border) — `auto_file` (UI label: "Auto-run (Kit acts autonomously)")

Sections stack — a single capture can check across all four. The new **web research** flag complements the two existing research flags for things that live outside the codebase (industry practice, vendor docs, comparative analysis). Auto-tags the resulting brain_dump/initiative with `web-research`.

Wire format kept stable. `flags.auto_file` is still the on-the-wire name; only the UI label changed. Future-me note: if a downstream consumer (Kit instructions, MCP tooling, queries) ever needs renaming, do it as a separate pass — UI/wire decoupling held the line on this one.

### Capture attachment ("Attach to existing capture")

New compose-form dropdown. Pick a recent pending queue item; the new capture becomes a child of that parent. One-deep — if you try to attach to a row that already has a parent, the attachment collapses to the grandparent so the tree never goes deeper than two levels.

Selecting a parent grays out the "What is this?" and "How Kit handles this" sections — those decisions belong to the parent. The child contributes its own content + source URL + any context/action flags. At triage time, Kit sees the composite (parent + all children) as ONE thing; resolving the parent resolves children too, unions their flag-derived tags, and concatenates source URLs into `source_metadata.source_urls`.

Schema impact: one new column, `triage_queue.parent_id`. Idempotent migration in `database.py:_migrate`.

New sidecar endpoints:
- `GET /triage-pending?limit=N` — populates the attach dropdown (top-level pending only, hides children)
- `GET /tangent-available` — host-level capability check used by the startup detection below

### Auto-run + tangent dispatch

`auto_file: true` no longer just files inline. When WezTerm + the tangent skill are present, Kit dispatches the whole composite (parent + children) to a fresh Claude tab via the `Skill` tool — `tangent-teach` for research-only flag sets, plain `tangent` when any action flag is involved. The new tab inherits Kit's cwd by default and gets a handoff blurb with all captured content, all source URLs, the unioned flag set, and `user_context`.

`settings.yaml` got a `tangent` block:

```yaml
tangent:
  enabled: auto              # auto | true | false. auto = detect at startup.
  skill_work: tangent
  skill_research: tangent-teach
  attach_dropdown_limit: 10
```

Detection (`shutil.which("wezterm")` + SKILL.md existence) runs through `briefcase/sidecar/server.py:detect_tangent_available` and `briefcase/mcp_server/config.py:resolve_tangent_config`. When detection fails (no WezTerm, or `enabled: false`), the auto-run sweep silently falls back to the previous inline filing behavior — no error, no user-visible difference, just no tangent.

New MCP tool **`get_runtime_capabilities`** exposes the result. Kit calls it once at the top of every triage walk and caches the answer.

### Kit / kit-lite instruction sync

Both `.claude/commands/kit.md` and `~/.dotfiles/claude/commands-work/kit-lite.md` updated to describe the new flow with a worked example showing the exact call sequence for an auto-run + research composite (the obvious wrong path — calling `triage_item(..., action='brain_dump')` inline — is called out explicitly). `SERVER_INSTRUCTIONS` in `server.py` kept in sync per the project's dual-instruction rule.

`kit.md` is now bound at user level via dotfiles' `command-bindings.conf` so `/kit` works from any cwd, sourced canonically from the BriefCase repo (no copy, no symlink-in-place — the binding row points at the live file).

### Files touched

- `extension/compose.html` (regrouped sections, new attach dropdown, new web-research checkbox)
- `extension/compose.js` (flag collection, attach inheritance, dropdown loader)
- `extension/background.js` (new `LIST_PENDING_TRIAGE` handler)
- `briefcase/sidecar/server.py` (`ClipIn.attach_to_id`, `/triage-pending`, `/tangent-available`)
- `briefcase/mcp_server/database.py` (`parent_id` column + migration, `get_triage_children`, `get_triage_item_with_children`, `resolve_triage_item_with_children`)
- `briefcase/mcp_server/tools/get_triage_queue.py` (nested children)
- `briefcase/mcp_server/tools/triage_item.py` (child cascade, flag-union, URL concat, refuse-child-direct guard, `web-research` tag mapping)
- `briefcase/mcp_server/tools/get_runtime_capabilities.py` (new)
- `briefcase/mcp_server/config.py` (`resolve_tangent_config`)
- `briefcase/mcp_server/server.py` (tool registration, `SERVER_INSTRUCTIONS` updates, version bump 0.12.0 → 0.13.0)
- `settings.yaml` (`tangent:` block)
- `.claude/commands/kit.md` (triage walk rewrite, web-research flag, composite handling, tangent dispatch)
- `~/.dotfiles/claude/commands-work/kit-lite.md` (matching rewrite + worked example)
- `~/.dotfiles/claude/command-bindings.conf` (new row: `kit.md` → `~/Programming/BriefCase/.claude/commands/kit.md`)

### Manual step after pulling

- **Reload the Chrome extension** at `chrome://extensions` so the new compose flow + attach dropdown wire in
- **Restart any open `/kit` or `/kit-lite` sessions** so they pick up the new instructions (command files are read at session start)

---

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
