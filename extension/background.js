// BriefCase Chrome extension — service worker.
//
// Registers right-click context menus and forwards captures to the local sidecar.
// Configure the sidecar URL and auth token on the options page.

const DEFAULT_SIDECAR_URL = "http://127.0.0.1:8989";

const MENU_ROOT = "briefcase-root";
const MENU_SEND_SELECTION = "briefcase-send-selection";
const MENU_SEND_PAGE = "briefcase-send-page";
const MENU_SEND_LINK = "briefcase-send-link";
const MENU_SEND_WITH_CONTEXT = "briefcase-send-with-context";

const PENDING_CAPTURE_KEY = "pendingCapture";

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
      id: MENU_ROOT,
      title: "BriefCase",
      contexts: ["selection", "page", "link"],
    });

    chrome.contextMenus.create({
      id: MENU_SEND_SELECTION,
      parentId: MENU_ROOT,
      title: "Send selection to BriefCase",
      contexts: ["selection"],
    });

    chrome.contextMenus.create({
      id: MENU_SEND_PAGE,
      parentId: MENU_ROOT,
      title: "Send this page to BriefCase",
      contexts: ["page"],
    });

    chrome.contextMenus.create({
      id: MENU_SEND_LINK,
      parentId: MENU_ROOT,
      title: "Send this link to BriefCase",
      contexts: ["link"],
    });

    chrome.contextMenus.create({
      id: "briefcase-separator",
      parentId: MENU_ROOT,
      type: "separator",
      contexts: ["selection", "page", "link"],
    });

    chrome.contextMenus.create({
      id: MENU_SEND_WITH_CONTEXT,
      parentId: MENU_ROOT,
      title: "Send with context...",
      contexts: ["selection", "page", "link"],
    });
  });
}

// ---- Menu click handling ----

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  try {
    if (info.menuItemId === MENU_SEND_WITH_CONTEXT) {
      await openComposeWindow(info, tab);
      return;
    }
    const clip = buildClip(info, tab);
    if (!clip) return;
    const result = await postClip(clip);
    await notify(
      "Sent to BriefCase",
      `Item #${result.triage_item_id} queued. Walk through it next time you open Kit.`
    );
  } catch (err) {
    console.error("BriefCase: capture failed", err);
    await notify("BriefCase error", String(err.message || err));
  }
});

// ---- Compose popup ----

async function openComposeWindow(info, tab) {
  // Build the base clip exactly the same way as the one-shot path.
  // Prefer selection context if text is selected, then link, then page.
  let effectiveMenuId = MENU_SEND_PAGE;
  if (info.selectionText) {
    effectiveMenuId = MENU_SEND_SELECTION;
  } else if (info.linkUrl) {
    effectiveMenuId = MENU_SEND_LINK;
  }
  const baseClip = buildClip({ ...info, menuItemId: effectiveMenuId }, tab);
  if (!baseClip) return;

  const capture_type =
    effectiveMenuId === MENU_SEND_SELECTION
      ? "selection_with_context"
      : effectiveMenuId === MENU_SEND_LINK
      ? "link_with_context"
      : "page_with_context";

  await chrome.storage.session.set({
    [PENDING_CAPTURE_KEY]: {
      baseClip,
      capture_type,
      source_title: tab?.title || null,
      source_url: baseClip.source_url || null,
      // Pre-fill content with whatever the one-shot path would have sent.
      initial_content: baseClip.content,
    },
  });

  chrome.windows.create({
    url: chrome.runtime.getURL("compose.html"),
    type: "popup",
    width: 620,
    height: 560,
    focused: true,
  });
}

function buildClip(info, tab) {
  const pageUrl = tab?.url || info.pageUrl || null;
  const pageTitle = tab?.title || null;

  switch (info.menuItemId) {
    case MENU_SEND_SELECTION: {
      if (!info.selectionText) return null;
      return {
        source: "web_clip",
        content: info.selectionText,
        source_url: pageUrl,
        title: pageTitle,
        metadata: {
          capture_type: "selection",
          frame_url: info.frameUrl || null,
        },
      };
    }
    case MENU_SEND_PAGE: {
      return {
        source: "web_clip",
        content: pageTitle || pageUrl || "(untitled page)",
        source_url: pageUrl,
        title: pageTitle,
        metadata: { capture_type: "page" },
      };
    }
    case MENU_SEND_LINK: {
      return {
        source: "web_clip",
        content: info.linkUrl || "",
        source_url: info.linkUrl || null,
        title: info.selectionText || info.linkUrl || pageTitle,
        metadata: {
          capture_type: "link",
          context_page_url: pageUrl,
          context_page_title: pageTitle,
        },
      };
    }
    default:
      return null;
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
        detail ? ` — ${detail}` : ""
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

// ---- Popup / options can ping this for a health check ----

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
    return true; // keep the channel open for async sendResponse
  }

  if (msg?.type === "SEND_WITH_CONTEXT") {
    (async () => {
      try {
        const result = await postClip(msg.clip);
        await notify(
          "Sent to BriefCase",
          `Item #${result.triage_item_id} queued with your added context.`
        );
        sendResponse({ ok: true, data: result });
      } catch (err) {
        console.error("BriefCase: compose send failed", err);
        sendResponse({ ok: false, error: String(err.message || err) });
      }
    })();
    return true;
  }

  return false;
});
