# BriefCase — New Machine Install

The long version of the `README.md` quick-start. If you're sitting in front of
a freshly-imaged work mac with nothing on it, this is the path.

---

## 0. Prerequisites

You need:

- **macOS** (tested on Sonoma+; the launchd sidecar is mac-specific)
- **Homebrew** (`brew --version` should work)
- **Python 3.11+** (`brew install python@3.12`)
- **Claude Code** (`brew install --cask claude-code`)
- **Google Chrome** (any recent version — Manifest V3 era)
- A GitHub account that can clone this repo

`setup.sh` checks for `python3` and `claude` and bails early if either is
missing. The other two it assumes.

---

## 1. Clone the repo

```bash
mkdir -p ~/Programming
cd ~/Programming
git clone <repo-url> BriefCase
cd BriefCase
```

The path `~/Programming/BriefCase` isn't load-bearing — `setup.sh` writes the
absolute path it sees into the MCP registration and the launchd plist — but
it's the convention on every other machine, so keep it unless you have a
reason.

---

## 2. Run the installer

```bash
./setup.sh
```

Roughly 30-60 seconds the first time, mostly pip. What it does:

| Phase | Action |
|---|---|
| 0 | Verifies `python3` and `claude` are on PATH. |
| 1 | Creates `venv/`, installs `requirements.txt`. |
| 2 | Creates `~/.briefcase/{backups,logs}`, initialises `briefcase.db`, writes a `user_profile.yaml` template if one isn't already there. |
| 3 | Registers the MCP server with Claude Code at **user scope** (so `/kit` works from any working directory). Idempotent — skips if already registered. |
| 4 | Delegates to `briefcase/sidecar/install.sh`, which installs the launchd plist and starts the sidecar. |
| 5 | Prints next steps + the sidecar auth token. |

If anything fails mid-run, fix it and re-run — every phase no-ops on the parts
that are already done.

---

## 3. Fill in your user profile

```bash
$EDITOR ~/.briefcase/user_profile.yaml
```

This is what Kit reads at the start of every conversation to know who you are.
At minimum set `name`, `role`, `team_name`, and at least one `projects:` entry
with a real `slug` / `name`. The slug is what you'll use in MCP calls like
`get_initiative_status(slug="insurance-management")`.

---

## 4. Load the Chrome extension

1. Open `chrome://extensions`.
2. Toggle **Developer mode** (top right).
3. Click **Load unpacked**.
4. Select `~/Programming/BriefCase/extension/`.
5. The BriefCase icon appears in the toolbar — pin it via the puzzle icon.

### Paste the auth token

1. Right-click the BriefCase icon → **Options**.
2. **Sidecar URL**: leave the default `http://127.0.0.1:8989`.
3. **Auth token**: paste the contents of `~/.briefcase/sidecar_token`:
   ```bash
   cat ~/.briefcase/sidecar_token | pbcopy
   ```
4. Click **Test connection**. Expected: `"Sidecar 0.1.0 — N pending in queue."`
5. **Save**.

### Bind a keyboard shortcut (optional, but worth it)

Chrome doesn't auto-bind anything. Open `chrome://extensions/shortcuts`, find
BriefCase → "Open the BriefCase compose popup", and press your preferred
combo. `⌘⇧Y` is the suggested default.

---

## 5. Restore your database (if you have a backup)

If you're moving from a previous machine, restore from the iCloud-mirrored
backup:

```bash
scripts/restore-db.sh --latest
```

That looks in both `~/.briefcase/backups/` (just-installed, empty) and
`~/Library/Mobile Documents/com~apple~CloudDocs/BriefCase-Backups/` (your
iCloud mirror), picks the newest file, verifies it, takes a safety snapshot
of the empty fresh DB, then restores.

If iCloud hasn't fully synced down yet, the script will show an empty list —
wait a bit and re-run, or pass the path explicitly.

If you're starting from scratch, skip this step. Kit will start empty and
build up state as you use it.

---

## 6. Restart the sidecar

If you restored a DB, the running sidecar is still holding the old (empty) one
open. Reload it:

```bash
launchctl unload ~/Library/LaunchAgents/com.briefcase.sidecar.plist
launchctl load -w ~/Library/LaunchAgents/com.briefcase.sidecar.plist
```

`/health` should now report the real `pending_count`.

---

## 7. Verify end-to-end

Quickest single-shot health check:

```bash
scripts/health-check.sh
```

Reports the status of every piece (venv, deps, DB, MCP, sidecar, token, launchd)
in one pass. Should be all `[ok]` lines and end with "Everything is healthy."

Then the real test — open a Claude Code session anywhere on disk:

```bash
cd ~/
claude
```

In the session:

```
/kit
```

You should see the standard Kit greeting — forecast, recent activity, queue
count. If you restored a DB, your initiatives, captures, and dailies will all
be there.

Then test capture:

1. Highlight some text on any web page.
2. Right-click → **BriefCase** → **Send to BriefCase...** (or `⌘⇧Y`).
3. Confirm in the compose popup → **Send**.
4. In Kit, ask "what's in the queue?" — your capture should be there.

---

## Recurring maintenance

There's not much to do on an ongoing basis. The pieces:

- **DB backups** — run `scripts/backup-db.sh` whenever you remember. I do it
  end-of-day on busy days and weekly otherwise. The iCloud mirror means even
  a single backup-a-week is fine durability.
- **Repo updates** — `git pull` and re-run `./setup.sh` if anything changed
  under `briefcase/`. Re-registering the MCP and reloading the sidecar are
  both idempotent.
- **Token rotation** — `rm ~/.briefcase/sidecar_token && bash
  briefcase/sidecar/install.sh` regenerates and prints the new token. Update
  the extension options.

---

## Uninstalling

If you really want it gone:

```bash
# Stop and remove the sidecar
launchctl unload ~/Library/LaunchAgents/com.briefcase.sidecar.plist
rm ~/Library/LaunchAgents/com.briefcase.sidecar.plist

# Unregister from Claude Code
claude mcp remove briefcase

# Remove runtime data (this nukes your DB and backups — be sure)
rm -rf ~/.briefcase

# Remove the repo
rm -rf ~/Programming/BriefCase
```

The Chrome extension you remove from `chrome://extensions` manually.
