# BriefCase Sidecar

## What this is

The **sidecar** is a small FastAPI HTTP server that runs on your Mac and listens on
`http://127.0.0.1:8989`. It exists solely to give the Chrome extension a target it can
POST captures to.

**Why it exists:** MCP servers (like the main `briefcase` MCP server) only run while
Claude Code is open and only speak over stdio. Browser extensions speak HTTP and need
an always-on endpoint. The sidecar bridges the gap. It writes to the same SQLite
database (`~/.briefcase/briefcase.db`) the MCP server uses, so captures land in the
`triage_queue` table and Kit picks them up at the next conversation start.

**It's not Kubernetes.** "Sidecar" is just an architecture pattern word — a helper
process that runs alongside a main one. Here the "main" thing is the browser; the
sidecar is a local helper.

---

## Architecture at a glance

```
┌─────────────────┐    POST /clip    ┌─────────────────┐
│  Chrome ext.    │ ───────────────▶ │  Sidecar        │
│  (user clicks   │   X-BriefCase-   │  FastAPI on     │
│   "Send to      │      Token       │  127.0.0.1:8989 │
│   BriefCase")   │                  └────────┬────────┘
└─────────────────┘                           │
                                              │ writes to
                                              ▼
                                   ┌─────────────────────┐
                                   │ ~/.briefcase/       │
                                   │   briefcase.db      │
                                   │   (triage_queue)    │
                                   └──────────┬──────────┘
                                              │ read via MCP
                                              ▼
                              ┌──────────────────────────────┐
                              │  Kit (Claude Code + MCP)     │
                              │  walks queue items 1x1       │
                              └──────────────────────────────┘
```

Sidecar and MCP server are independent processes. They share the DB, never talk
directly. SQLite handles concurrent access.

---

## Install / reinstall

First-time install: just run the root `./setup.sh` — it calls this installer as
phase 4. The standalone command is for re-runs:

```bash
bash briefcase/sidecar/install.sh
```

The installer is idempotent either way. It:

1. Confirms the Python venv has FastAPI installed (runs `pip install` if missing).
2. Generates `~/.briefcase/sidecar_token` if it doesn't exist yet (32 random url-safe
   bytes, 600 perms). **Save this token — the Chrome extension needs it.**
3. Renders `com.briefcase.sidecar.plist` with your actual paths and installs it to
   `~/Library/LaunchAgents/`.
4. `launchctl load`s it so the sidecar starts immediately and at every login.

Re-run it after moving the project directory, changing the venv, or rotating the
token. It prints the current token at the end.

---

## Day-to-day operations

All commands below assume the default label `com.briefcase.sidecar` and plist path
`~/Library/LaunchAgents/com.briefcase.sidecar.plist`.

### Check if it's running

```bash
launchctl list | grep briefcase
```

If running, you'll see a line like:
```
60129  0  com.briefcase.sidecar
```

The middle column is the last exit status (0 = healthy, non-zero = it crashed
recently). The left column is the current PID, or `-` if not currently running.

You can also hit the health endpoint (no auth required):

```bash
curl http://127.0.0.1:8989/health
```

Response:
```json
{"status":"ok","version":"0.1.0","pending_count":3}
```

### Stop the sidecar

```bash
launchctl unload ~/Library/LaunchAgents/com.briefcase.sidecar.plist
```

This stops it **and** prevents it from starting at next login. Re-enable with `load -w`.

### Restart the sidecar

```bash
launchctl unload ~/Library/LaunchAgents/com.briefcase.sidecar.plist
launchctl load -w ~/Library/LaunchAgents/com.briefcase.sidecar.plist
```

Do this after:
- Editing `settings.yaml` `sidecar:` section (port changes)
- Updating `server.py` or anything it imports
- Rotating the token

### Uninstall entirely

```bash
launchctl unload ~/Library/LaunchAgents/com.briefcase.sidecar.plist
rm ~/Library/LaunchAgents/com.briefcase.sidecar.plist
```

Leave the DB and token alone — they're not owned by the sidecar; the MCP server also
uses the DB.

---

## Logs

```
~/.briefcase/logs/sidecar.log   # stdout (request logs, info)
~/.briefcase/logs/sidecar.err   # stderr (errors, crashes)
```

Tail them live:

```bash
tail -f ~/.briefcase/logs/sidecar.log ~/.briefcase/logs/sidecar.err
```

If the process crashes at boot, `.err` is where to look first.

---

## Auth token

Stored at `~/.briefcase/sidecar_token` with mode `0600`. Every `POST /clip` must
include:

```
X-BriefCase-Token: <token contents>
```

`GET /health` is unauthenticated by design — useful for the extension to check
"is the sidecar up?" without needing the token.

### Rotate the token

```bash
rm ~/.briefcase/sidecar_token
bash briefcase/sidecar/install.sh    # regenerates and reloads
```

Then update the token in the Chrome extension's options/config.

---

## Endpoints

### `GET /health`

No auth. Returns:

```json
{"status":"ok","version":"0.1.0","pending_count":3}
```

`pending_count` is the number of triage_queue items awaiting processing.

### `POST /clip`

Auth required. JSON body:

```json
{
  "source": "google_chat",
  "content": "Message body or selected text",
  "source_url": "https://chat.google.com/room/abc/msg/xyz",
  "title": "Message from Alice in #eng",
  "metadata": {
    "sender": "Alice",
    "channel": "#eng",
    "timestamp": "2026-04-20T13:00:00Z",
    "thread_preview": ["msg 1", "msg 2"]
  }
}
```

Fields:

| Field | Required | Notes |
|---|---|---|
| `source` | yes | Short source type tag. Examples: `google_chat`, `web_clip`, `slack`. Max 64 chars. |
| `content` | yes | The captured text. Max 50,000 chars. |
| `source_url` | no | Permalink. Preserved on the final brain dump / initiative so Kit can render "open in source" later. |
| `title` | no | Page title, channel name, or anything else humans need at a glance. |
| `metadata` | no | Free-form JSON. Stored serialized on the queue item; carried onto brain dumps and initiatives at triage time. |

Response (201 Created):

```json
{"status":"success","triage_item_id":42}
```

Errors:
- `401` — missing or wrong `X-BriefCase-Token`
- `422` — invalid body (schema violation)
- `503` — sidecar token file missing (run install.sh)

---

## Testing from the terminal

```bash
TOKEN=$(cat ~/.briefcase/sidecar_token)

# Health
curl http://127.0.0.1:8989/health

# Manual clip
curl -X POST http://127.0.0.1:8989/clip \
    -H 'Content-Type: application/json' \
    -H "X-BriefCase-Token: $TOKEN" \
    -d '{
        "source": "web_clip",
        "content": "Sample capture from curl",
        "source_url": "https://example.com",
        "title": "Example page"
    }'
```

Then open Kit and ask "what's in the queue?" — you'll see the item.

---

## Troubleshooting

**`curl: (7) Failed to connect to 127.0.0.1 port 8989`**
Sidecar isn't running. `launchctl list | grep briefcase`. If nothing, run install.sh.
If the middle column (last exit) is non-zero, check `~/.briefcase/logs/sidecar.err`.

**`{"detail":"Invalid or missing X-BriefCase-Token header."}`**
Token mismatch. Compare `cat ~/.briefcase/sidecar_token` with what the Chrome
extension is sending. If you rotated the token, re-configure the extension.

**Port already in use**
Something else is on 8989. Change the port in `settings.yaml` under `sidecar:`, then
restart. Or set `BRIEFCASE_SIDECAR_PORT` in the plist's `EnvironmentVariables` block.

**Sidecar starts but immediately crashes**
Check `~/.briefcase/logs/sidecar.err`. Common causes:
- Missing FastAPI — install.sh should have handled this; run it again
- Corrupted DB — check permissions on `~/.briefcase/briefcase.db`
- Settings.yaml is malformed YAML

**Changed code but behavior didn't change**
launchd caches the running process. `launchctl unload ... && launchctl load -w ...`
after any code change.

---

## Configuration reference

Port precedence (highest first):
1. `BRIEFCASE_SIDECAR_PORT` env var
2. `settings.yaml` → `sidecar.port`
3. Built-in default: `8989`

Bind address: always `127.0.0.1` (localhost-only). Intentional — do not expose this
to the network. The only auth is a shared secret token; it's not hardened for
internet exposure.

Files created/owned by the sidecar:
- `~/.briefcase/sidecar_token` — auth token, 600 perms
- `~/.briefcase/logs/sidecar.log` — stdout
- `~/.briefcase/logs/sidecar.err` — stderr
- `~/Library/LaunchAgents/com.briefcase.sidecar.plist` — launchd definition

Files the sidecar reads/writes but doesn't own:
- `~/.briefcase/briefcase.db` — SQLite database (shared with MCP server)
- `<project>/settings.yaml` — for the `sidecar:` block

---

## File layout

```
briefcase/sidecar/
├── __init__.py
├── server.py                                   # FastAPI app + entrypoint
├── install.sh                                  # idempotent installer
├── launchd/
│   └── com.briefcase.sidecar.plist.template    # plist template with placeholders
└── README.md                                   # this file
```
