// BriefCase Chrome extension — service worker.
//
// All captures go through the compose popup (right-click menu or keyboard
// shortcut). The popup lets you edit the content, override the source URL
// (e.g. paste a specific Google Chat message permalink), and add context
// beneath a divider before sending.

const DEFAULT_SIDECAR_URL = "http://127.0.0.1:8989";

const MENU_SEND = "briefcase-send";

const PENDING_CAPTURE_KEY = "pendingCapture";

const COMPOSE_WIDTH = 660;
const COMPOSE_HEIGHT = 760;

// ---- Lifecycle ----

chrome.runtime.onInstalled.addListener(() => {
  registerMenus();
});

// Service workers go to sleep; rebuild menus on startup too.
chrome.runtime.onStartup.addListener(() => {
  registerMenus();
});

function registerMenus() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: MENU_SEND,
      title: "Send to BriefCase...",
      contexts: ["selection", "page", "link"],
    });
  });
}

// ---- Menu click handling ----

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  try {
    if (info.menuItemId === MENU_SEND) {
      await openComposeWindow({
        selectionText: info.selectionText || null,
        linkUrl: info.linkUrl || null,
        frameUrl: info.frameUrl || null,
        pageUrl: info.pageUrl || tab?.url || null,
        tab,
      });
    }
  } catch (err) {
    console.error("BriefCase: menu capture failed", err);
    await notify("BriefCase error", String(err.message || err));
  }
});

// ---- Keyboard shortcut ----
//
// Configure the binding at chrome://extensions/shortcuts.

chrome.commands.onCommand.addListener(async (command) => {
  if (command !== "open_compose") return;
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) return;

    let selectionText = null;
    try {
      const [result] = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => window.getSelection()?.toString() || "",
      });
      selectionText = (result?.result || "").trim() || null;
    } catch (err) {
      // Some pages (chrome://, web store) block scripting. Continue without selection.
      console.warn("BriefCase: could not read selection", err);
    }

    await openComposeWindow({
      selectionText,
      linkUrl: null,
      frameUrl: null,
      pageUrl: tab.url || null,
      tab,
    });
  } catch (err) {
    console.error("BriefCase: hotkey capture failed", err);
    await notify("BriefCase error", String(err.message || err));
  }
});

// ---- Compose popup ----

async function openComposeWindow({ selectionText, linkUrl, frameUrl, pageUrl, tab }) {
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

  chrome.windows.create({
    url: chrome.runtime.getURL("compose.html"),
    type: "popup",
    width: COMPOSE_WIDTH,
    height: COMPOSE_HEIGHT,
    focused: true,
  });
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

// ---- Message handlers (popup + compose) ----

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

// ---- Sidecar draft endpoint ----

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
