# BriefCase Chrome Extension

## What this does

Right-click on any web page → **BriefCase** → choose one of:
- **Send selection to BriefCase** (when text is highlighted)
- **Send this page to BriefCase** (captures page URL + title)
- **Send this link to BriefCase** (when right-clicking a link)

The capture POSTs to your local sidecar (`http://127.0.0.1:8989`), which writes it
into Kit's `triage_queue`. Next time you open Kit, it'll notice and offer to walk you
through each item — decide per-item whether it becomes a brain dump, new initiative,
ThriveNote, daily-note entry, or discard.

This is v1 (generic capture). The Google Chat adapter — which grabs message text,
sender, permalink, and optional thread context — is coming in v1.5.

---

## Prerequisites

The sidecar needs to be running. On a fresh machine the root `./setup.sh` starts
it for you and prints the auth token. If you've already done that, skip ahead to
"Install the extension" below. Otherwise, install just the sidecar standalone:

```bash
bash briefcase/sidecar/install.sh
```

Either command prints your auth token at the end. Copy it — you'll paste it into
the extension options below.

---

## Install the extension (unpacked)

1. Open Chrome and navigate to `chrome://extensions`.
2. Toggle **Developer mode** on (top-right corner).
3. Click **Load unpacked**.
4. Select this directory: `/Users/brendan.roman/Programming/BriefCase/extension/`.
5. The BriefCase icon should appear in the toolbar (pin it via the puzzle-piece menu
   if you want quick access).

### Configure the token

1. Right-click the BriefCase icon → **Options** (or click the icon to open the
   side panel and use the "options" link in the top-right).
2. **Sidecar URL**: leave the default `http://127.0.0.1:8989` unless you changed
   the port in `settings.yaml`.
3. **Auth token**: paste the contents of `~/.briefcase/sidecar_token`. Tip:
   ```bash
   cat ~/.briefcase/sidecar_token | pbcopy
   ```
4. Click **Test connection**. You should see "Sidecar 0.1.0 — N pending in queue."
5. Click **Save**.

---

## Using it

All captures go through the BriefCase side panel so you always see the URL
before sending and can add context.

### Three ways to open the side panel

1. **Click the BriefCase toolbar icon** — opens the panel (no popup intermediate).
2. **Right-click → Send to BriefCase...** on any selection, page, or link.
3. **Keyboard shortcut** (after you set it). Default suggestion: `⌘⇧Y` on macOS,
   `Ctrl+Shift+Y` on Windows/Linux. Chrome does NOT auto-assign the binding -
   you set it yourself at `chrome://extensions/shortcuts` (find BriefCase, click
   the pencil next to "Open the BriefCase side panel", press your keys).

### What the side panel does

- **Health widget** at the top — sidecar version + pending queue count.
- **Page title** shown next, with favicon (read-only, just for context).
- **Source link** — editable URL field. On open:
   - If your **clipboard** holds a URL, it auto-populates the field.
     Typical flow on Google Chat: hover a message → **More actions** (three dots) →
     **Copy message link**, then trigger BriefCase. The panel will detect
     that specific message permalink and use it as the source URL.
   - Otherwise, it falls back to the current page URL (room-level on Chat, just
     the page URL elsewhere).
   - An inline hint tells you what kind of URL is being used:
     **Google Chat message permalink (specific anchor)** - you got the precise
     message link.
     **Google Chat page (room-level, not message-specific)** - the fallback.
     **URL** - some other URL (page URL, a link you copied, etc.).
   - You can edit the field freely. Clear it and type your own.
- **Captured content** — the selection, pre-filled, editable.
- **Additional context** — optional free-form notes beneath a
  `---- additional context ----` divider. Stored separately in
  `metadata.user_context` so Kit can surface it distinctly.
- **Send** (⌘↩), **Draft now** (⌘D), or **Clear** to reset the form.

The panel persists across tab switches — your half-filled compose form stays
put until you send it or clear it.

### Google Chat workflow for best precision

1. Hover the message you want to capture.
2. Click **More actions** (three dots) → **Copy message link**. Clipboard now holds
   the specific permalink like
   `https://chat.google.com/dm/<room>/<thread>/<msg>?cls=10`.
3. Highlight the message text.
4. Hit your BriefCase shortcut (or right-click → BriefCase → Send to BriefCase...).
5. The side panel opens with the permalink already in the URL field. Send.

Then when you open Kit, tell it "triage" and it'll walk you through each item 1x1.

---

## Troubleshooting

**"Auth token not configured"** notification
Open the options page and paste the token. Click Save.

**"Sidecar returned 401"**
Token mismatch. Re-copy the token from `~/.briefcase/sidecar_token` and repaste.

**"Can't reach sidecar"**
Sidecar isn't running. Check: `launchctl list | grep briefcase`. If it's not there
or crashed, see `briefcase/sidecar/README.md` for recovery steps.

**Context menu doesn't appear**
- Reload the extension: `chrome://extensions` → click the reload button on the
  BriefCase card.

**Keyboard shortcut does nothing**
Chrome doesn't auto-assign shortcuts. Go to `chrome://extensions/shortcuts`, find
BriefCase, and set the keys yourself. If the suggested combo conflicts with
something else on your system, Chrome shows an empty field instead of applying it.

**Clipboard didn't auto-populate the URL field**
- The panel only auto-reads the clipboard on hydrate (to honor the "Copy
  message link" flow). If you copy a URL while the panel is already showing
  a capture, paste it manually.
- Chrome may block `navigator.clipboard.readText()` in rare cases (e.g. if the
  panel doesn't have focus). Click into the panel and re-trigger the capture.
- Make sure the page isn't a privileged Chrome page (chrome://, chrome-extension://,
  or the Chrome Web Store — extensions can't inject into those).

**Changes to the code aren't showing up**
Reload the extension at `chrome://extensions`. Chrome caches extension code
aggressively; the reload button is the fix.

---

## File layout

```
extension/
├── manifest.json       # MV3 manifest
├── background.js       # Service worker: menus + sidePanel + HTTP + notifications
├── options.html        # Options page (set URL + token, test connection)
├── options.js
├── sidepanel.html      # Side panel: health widget + compose form
├── sidepanel.js
├── sidepanel.css
├── themes.css          # Shared theme variables
├── theme.js            # Shared theme loader
├── icons/              # Simple PNG icons (16/48/128)
└── README.md           # This file
```

---

## Development notes

- **Manifest V3.** Service worker, no persistent background page. The worker goes to
  sleep between events — context menus are rebuilt in `chrome.runtime.onStartup` and
  `onInstalled` so they always exist.
- **Storage**: `chrome.storage.sync` for the sidecar URL and token. Syncs across
  Chrome instances (fine for single-user-per-device setups).
- **Permissions**: `contextMenus`, `storage`, `notifications`, `activeTab`,
  `scripting`. `host_permissions` is scoped to `http://127.0.0.1:8989/*` so Chrome
  allows the fetch without CORS drama.
- **Security posture**: Token auth + localhost-only server. Don't open the sidecar to
  the network. Don't share the token.
