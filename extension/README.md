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

Install and start the sidecar first:

```bash
bash briefcase/sidecar/install.sh
```

That command prints your auth token at the end. Copy it — you'll paste it into the
extension options below.

---

## Install the extension (unpacked)

1. Open Chrome and navigate to `chrome://extensions`.
2. Toggle **Developer mode** on (top-right corner).
3. Click **Load unpacked**.
4. Select this directory: `/Users/brendan.roman/Programming/BriefCase/extension/`.
5. The BriefCase icon should appear in the toolbar (pin it via the puzzle-piece menu
   if you want quick access).

### Configure the token

1. Right-click the BriefCase icon → **Options** (or click the icon, then "Open
   options" in the popup).
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

**One-shot captures (no popup):**
- Highlight text on any page → right-click → **BriefCase → Send selection to
  BriefCase**. A brief notification confirms the capture and gives you the triage
  item ID.
- For a whole page with no selection: right-click anywhere on the page → **BriefCase →
  Send this page to BriefCase**.
- For a link: right-click on the link → **BriefCase → Send this link to BriefCase**.

**Capture with added context (popup):**
- Right-click on any selection, page, or link → **BriefCase → Send with context...**
- A small popup window opens with:
  - Source preview (URL + title, read-only)
  - Editable "Captured content" textarea — pre-filled with the selection (or page /
    link info). Edit freely before sending.
  - "Additional context" textarea — add your own note beneath a
    `---- additional context ----` divider (why you're capturing, what's the ask,
    deadline, related initiative, etc.).
  - Send (**⌘↩**) / Cancel (**Esc**) buttons.
- The sidecar receives a combined payload: the edited content plus your context
  appended under the divider. Your context is also stored separately in
  `metadata.user_context` so Kit can surface it distinctly.

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
├── background.js       # Service worker: menus + HTTP + notifications
├── options.html        # Options page (set URL + token, test connection)
├── options.js
├── popup.html          # Toolbar popup (live sidecar status)
├── popup.js
├── compose.html        # "Send with context" popup
├── compose.js
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
