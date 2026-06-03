// BriefCase Chrome extension — service worker.
//
// All captures route through the side panel. Three entry points open the
// panel and pre-fill it with whatever context the user gesture surfaced:
//
//   - Toolbar action click (handled by setPanelBehavior)
//   - Right-click context menu ("Send to BriefCase...")
//   - Keyboard shortcut (Cmd/Ctrl+Shift+Y)
//
// IMPORTANT: chrome.sidePanel.open() MUST be called synchronously from the
// user-gesture context. Any await before it loses the gesture token and the
// call silently fails. Pattern: open the panel FIRST, then run the async
// selection-fetch chain and stash the result in chrome.storage.session for
// the panel to pick up on hydrate.

const DEFAULT_SIDECAR_URL = "http://127.0.0.1:8989";

const MENU_SEND = "briefcase-send";

const PENDING_CAPTURE_KEY = "pendingCapture";

// ---- Lifecycle ----

chrome.runtime.onInstalled.addListener(() => {
  registerMenus();
  enableSidePanelOnActionClick();
});

// Service workers go to sleep; rebuild menus + panel behavior on startup too.
chrome.runtime.onStartup.addListener(() => {
  registerMenus();
  enableSidePanelOnActionClick();
});

function enableSidePanelOnActionClick() {
  // Makes the toolbar icon open the side panel directly. No popup involved.
  if (chrome.sidePanel?.setPanelBehavior) {
    chrome.sidePanel
      .setPanelBehavior({ openPanelOnActionClick: true })
      .catch((err) => console.warn("BriefCase: setPanelBehavior failed", err));
  }
}

function registerMenus() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: MENU_SEND,
      title: "Send to BriefCase...",
      contexts: ["selection", "page", "link"],
    });
  });
}

// ---- Entry points ----

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId !== MENU_SEND) return;
  // Open synchronously to preserve the gesture token, THEN do the async
  // capture-prep work.
  openPanelSync(tab);
  stashCaptureFromMenu(info, tab).catch((err) => {
    console.error("BriefCase: menu capture failed", err);
    notify("BriefCase error", String(err.message || err));
  });
});

chrome.commands.onCommand.addListener((command) => {
  if (command === "open_compose") {
    chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
      if (!tab) return;
      openPanelSync(tab);
      stashCaptureFromHotkey(tab).catch((err) => {
        console.error("BriefCase: hotkey capture failed", err);
        notify("BriefCase error", String(err.message || err));
      });
    });
    return;
  }
  if (command === "close_panel") {
    chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
      if (!tab) return;
      try { chrome.sidePanel.close({ windowId: tab.windowId }); }
      catch (err) { console.error("BriefCase: sidePanel.close failed", err); }
    });
    return;
  }
});

function openPanelSync(tab) {
  if (!chrome.sidePanel?.open) {
    console.warn("BriefCase: chrome.sidePanel.open not available");
    return;
  }
  try {
    if (tab?.windowId != null) {
      chrome.sidePanel.open({ windowId: tab.windowId });
    } else if (tab?.id != null) {
      chrome.sidePanel.open({ tabId: tab.id });
    }
  } catch (err) {
    console.error("BriefCase: sidePanel.open failed", err);
  }
}

// ---- Capture prep ----

async function stashCaptureFromMenu(info, tab) {
  await stashPendingCapture({
    selectionText: info.selectionText || null,
    linkUrl: info.linkUrl || null,
    frameUrl: info.frameUrl || null,
    pageUrl: info.pageUrl || tab?.url || null,
    tab,
  });
}

async function stashCaptureFromHotkey(tab) {
  let selectionText = null;
  try {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => window.getSelection()?.toString() || "",
    });
    selectionText = (result?.result || "").trim() || null;
  } catch (err) {
    // Some pages (chrome://, web store) block scripting. Continue without.
    console.warn("BriefCase: could not read selection", err);
  }
  await stashPendingCapture({
    selectionText,
    linkUrl: null,
    frameUrl: null,
    pageUrl: tab.url || null,
    tab,
  });
}

async function stashPendingCapture({ selectionText, linkUrl, frameUrl, pageUrl, tab }) {
  const pageTitle = tab?.title || null;

  // Decide effective capture type based on what's available.
  let capture_type = "page_with_context";
  let initial_content = pageTitle || pageUrl || "";
  let initial_source_url = pageUrl;

  if (selectionText) {
    capture_type = "selection_with_context";
    initial_content = selectionText;
    initial_source_url = pageUrl;
  } else if (linkUrl) {
    capture_type = "link_with_context";
    initial_content = linkUrl;
    initial_source_url = linkUrl;
  }

  const baseMetadata = {
    capture_type,
    frame_url: frameUrl || null,
    page_url: pageUrl || null,
    page_title: pageTitle || null,
  };
  if (linkUrl) baseMetadata.link_url = linkUrl;

  const baseClip = {
    source: "web_clip",
    content: initial_content,
    source_url: initial_source_url,
    title: pageTitle,
    metadata: baseMetadata,
  };

  await chrome.storage.session.set({
    [PENDING_CAPTURE_KEY]: {
      baseClip,
      capture_type,
      source_title: pageTitle,
      source_url: initial_source_url,
      initial_content,
    },
  });

  // Nudge the side panel to hydrate. If it isn't open yet, this is a no-op
  // (no listeners). When it loads, it reads chrome.storage.session itself.
  try {
    await chrome.runtime.sendMessage({ type: "HYDRATE_PENDING" });
  } catch (_e) {
    // No receiver yet — panel will hydrate on its DOMContentLoaded path.
  }
}

// ---- Sidecar HTTP ----

async function getSidecarConfig() {
  const { sidecarUrl, authToken } = await chrome.storage.sync.get([
    "sidecarUrl",
    "authToken",
  ]);
  return {
    url: sidecarUrl || DEFAULT_SIDECAR_URL,
    token: authToken || "",
  };
}

async function postClip(clip) {
  const { url, token } = await getSidecarConfig();
  if (!token) {
    throw new Error(
      "Auth token not configured. Open the BriefCase extension options and paste your token."
    );
  }

  const response = await fetch(`${url}/clip`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-BriefCase-Token": token,
    },
    body: JSON.stringify(clip),
  });

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(
      `Sidecar returned ${response.status} ${response.statusText}${
        detail ? ` - ${detail}` : ""
      }`
    );
  }

  return response.json();
}

async function postDraft(payload) {
  const { url, token } = await getSidecarConfig();
  if (!token) {
    throw new Error(
      "Auth token not configured. Open the BriefCase extension options and paste your token."
    );
  }
  const response = await fetch(`${url}/draft`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-BriefCase-Token": token,
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(
      `Sidecar /draft returned ${response.status}${detail ? ` - ${detail}` : ""}`
    );
  }
  return response.json();
}

// ---- Notifications ----

async function notify(title, message) {
  try {
    await chrome.notifications.create({
      type: "basic",
      iconUrl: chrome.runtime.getURL("icons/icon-128.png"),
      title,
      message: message.slice(0, 240),
    });
  } catch (err) {
    console.warn("BriefCase: notification failed", err);
  }
}

// ---- Message handlers (side panel) ----

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "HEALTH_CHECK") {
    (async () => {
      try {
        const { url } = await getSidecarConfig();
        const r = await fetch(`${url}/health`);
        const data = await r.json();
        sendResponse({ ok: true, data });
      } catch (err) {
        sendResponse({ ok: false, error: String(err.message || err) });
      }
    })();
    return true;
  }

  if (msg?.type === "SEND_CLIP") {
    (async () => {
      try {
        const result = await postClip(msg.clip);
        await notify(
          "Sent to BriefCase",
          `Item #${result.triage_item_id} queued.`
        );
        sendResponse({ ok: true, data: result });
      } catch (err) {
        console.error("BriefCase: send failed", err);
        sendResponse({ ok: false, error: String(err.message || err) });
      }
    })();
    return true;
  }

  if (msg?.type === "LIST_PENDING_TRIAGE") {
    (async () => {
      try {
        const { url, token } = await getSidecarConfig();
        if (!token) throw new Error("Auth token not configured.");
        const limit = Math.max(1, Math.min(parseInt(msg.limit, 10) || 10, 50));
        const r = await fetch(`${url}/triage-pending?limit=${limit}`, {
          headers: { "X-BriefCase-Token": token },
        });
        if (!r.ok) {
          const detail = await r.text().catch(() => "");
          throw new Error(`Sidecar /triage-pending returned ${r.status}${detail ? ` - ${detail}` : ""}`);
        }
        const data = await r.json();
        sendResponse({ ok: true, data });
      } catch (err) {
        console.warn("BriefCase: list pending triage failed", err);
        sendResponse({ ok: false, error: String(err.message || err) });
      }
    })();
    return true;
  }

  if (msg?.type === "DRAFT_REPLY") {
    (async () => {
      try {
        const result = await postDraft(msg.payload);
        sendResponse({ ok: true, data: result });
      } catch (err) {
        console.error("BriefCase: draft failed", err);
        sendResponse({ ok: false, error: String(err.message || err) });
      }
    })();
    return true;
  }

  return false;
});
