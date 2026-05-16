# BriefCase

BriefCase is the MCP server, sidecar, and Chrome extension that power **Kit** —
my work-focused planning assistant inside Claude Code. It captures brain dumps,
tracks initiatives, plans the day, and stitches Claude Code sessions together
with persistent state.

This repo is everything you need to stand it up on a fresh Mac.

---

## Quick start

```bash
git clone <this-repo> ~/Programming/BriefCase
cd ~/Programming/BriefCase
./setup.sh
```

That's it for the install side. The script is idempotent — re-run it any time
something looks off.

After `setup.sh` finishes you still need to:

1. Edit `~/.briefcase/user_profile.yaml` with your real role / team / projects.
2. Load the Chrome extension as **unpacked** (`chrome://extensions` →
   Developer mode → Load unpacked → `extension/`).
3. Paste the printed sidecar token into the extension options page.
4. (Optional but recommended) Restore your DB from a backup:
   ```bash
   scripts/restore-db.sh --latest
   ```
5. Open Claude Code anywhere and run `/kit` to verify.

Full walkthrough: [`docs/INSTALL.md`](docs/INSTALL.md).

---

## Architecture

```
┌──────────────────┐   POST /clip    ┌──────────────────┐
│  Chrome ext.     │ ──────────────▶ │  Sidecar         │
│  (compose popup) │                 │  FastAPI @ 8989  │
└──────────────────┘                 └────────┬─────────┘
                                              │
                                              ▼
                                   ┌──────────────────────┐
                                   │  ~/.briefcase/       │
                                   │    briefcase.db      │  ◀── shared
                                   └──────────┬───────────┘
                                              │
                              ┌───────────────┴────────────────┐
                              ▼                                ▼
                  ┌──────────────────────┐         ┌────────────────────┐
                  │  MCP server          │         │  scripts/          │
                  │  (briefcase.mcp_     │         │  backup-db.sh      │
                  │   server) — invoked  │         │  restore-db.sh     │
                  │  by Claude Code      │         └────────────────────┘
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │  Kit agent (.claude/ │
                  │  commands/kit.md)    │
                  └──────────────────────┘
```

Three independent processes share one SQLite file. The sidecar runs forever as
a launchd agent so the browser always has somewhere to POST. The MCP server is
spawned per-conversation by Claude Code. SQLite handles concurrent access.

**The DB at `~/.briefcase/briefcase.db` is the source of truth.** Initiatives,
brain dumps, decisions, daily notes, triage queue — all live there. Back it up.

---

## What lives where

| Path | What it is |
|---|---|
| `setup.sh` | One-command installer (idempotent). |
| `briefcase/mcp_server/` | The MCP server Kit talks to. One tool per file in `tools/`. |
| `briefcase/sidecar/` | FastAPI bridge for the Chrome extension. Has its own `install.sh` for the launchd agent. |
| `extension/` | Chrome extension (Manifest V3). Loaded unpacked. |
| `.claude/commands/kit.md` | The Kit agent instructions (full version — `SERVER_INSTRUCTIONS` in `server.py` must stay in sync). |
| `scripts/backup-db.sh` | Snapshot the DB. Mirrors to iCloud Drive if available. |
| `scripts/restore-db.sh` | Restore from a backup, with a safety snapshot of the current DB first. |
| `settings.yaml` | Feature flags, paths, sidecar port. |
| `docs/INSTALL.md` | New-machine walkthrough. |
| `CHANGELOG.md` | Release / capability log. |

Runtime data — none of which is tracked by git — lives at `~/.briefcase/`:

| Path | What it is |
|---|---|
| `briefcase.db` | The SQLite file. *Back this up.* |
| `backups/` | Local backups from `backup-db.sh` (and pre-restore safety snapshots). |
| `logs/sidecar.{log,err}` | Sidecar stdout / stderr. |
| `sidecar_token` | Shared secret between extension and sidecar. Never commit. |
| `user_profile.yaml` | Your role, team, projects. Kit reads this every conversation. |
| `last_draft.txt` | Last `/draft` output, restored by the `recopy` shell function. |

---

## DB backup & restore

The DB is the only thing that won't reconstitute itself from the repo. Treat it
like you'd treat your `~/.zsh_history` — back it up somewhere off the laptop.

**Recommended:** `scripts/backup-db.sh` mirrors to iCloud Drive automatically if
it sees `~/Library/Mobile Documents/com~apple~CloudDocs/` (i.e. iCloud Drive is
turned on for your user). No extra tooling, no second repo, no separate cloud
account — the file is just a file. On a new mac you log in, iCloud syncs the
mirror down, you run `scripts/restore-db.sh --latest`, done.

```bash
scripts/backup-db.sh              # one-shot snapshot
scripts/backup-db.sh --local      # skip iCloud (offline / sensitive moment)
scripts/restore-db.sh             # interactive picker
scripts/restore-db.sh --latest    # newest backup we can find
scripts/restore-db.sh <path>      # restore a specific file
```

I run it ad-hoc rather than on a schedule. If you want it scheduled, drop a
launchd plist that runs `backup-db.sh` once a day — the script is safe to run
against a live DB (it uses SQLite's online backup API, not `cp`).

---

## Troubleshooting

**First stop**: `scripts/health-check.sh`. Reports the status of every piece —
venv, dependencies, DB integrity, MCP registration, sidecar, token, launchd —
in one pass. Useful right after install and any time something looks off.

**`/kit` says "no MCP server"**
Check `claude mcp list | grep briefcase`. If it's absent, re-run `./setup.sh`
(phase 3 registers it at user scope so it's reachable from any working
directory). If it's there but failing, check the `command` and `args` paths
— they should point at `<repo>/venv/bin/python` and
`<repo>/briefcase/mcp_server/server.py`. Moving the repo invalidates them.

**Chrome extension can't reach the sidecar**
`curl http://127.0.0.1:8989/health` from your terminal. If that fails, the
sidecar isn't running — `launchctl list | grep briefcase`. See
[`briefcase/sidecar/README.md`](briefcase/sidecar/README.md) for the deeper
diagnostic flow.

**"Invalid or missing X-BriefCase-Token"**
The extension and the sidecar are out of sync on the token. `cat
~/.briefcase/sidecar_token | pbcopy`, paste into the extension options, save.

**I moved the repo and now nothing works**
The MCP registration and the launchd plist both hard-code absolute paths.
Re-run `./setup.sh` from the new location — it'll re-register the MCP and
re-render the plist with the new paths.

**The DB is corrupted / I want to roll back to yesterday**
`scripts/restore-db.sh` — pick a backup. The script takes a safety snapshot of
the current DB before overwriting, so the roll-back itself is reversible.

---

## Working on BriefCase itself

If you're editing the MCP server, restart it so Claude Code picks up the new
code:

```bash
scripts/restart-mcp-server.sh
```

If you're editing the sidecar, reload the launchd agent:

```bash
launchctl unload ~/Library/LaunchAgents/com.briefcase.sidecar.plist
launchctl load -w ~/Library/LaunchAgents/com.briefcase.sidecar.plist
```

The Kit agent instructions live in **two** places that must stay in sync:
`.claude/commands/kit.md` (the full agent prompt) and `SERVER_INSTRUCTIONS` in
`briefcase/mcp_server/server.py` (the short version sent to every MCP client).
When you change one, change both. There's a note about this in `CLAUDE.md`.
