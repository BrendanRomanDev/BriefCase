// BriefCase side panel.
//
// Single persistent surface for capture. Hosts:
//   - Health widget (sidecar reachable + version + pending count)
//   - Compose form (edit content, override source URL, set flags, send)
//
// State lives globally (not per-tab). The form persists across tab switches.
// On open / DOMContentLoaded we hydrate any pending capture stashed by the
// background service worker in chrome.storage.session.

const PENDING_CAPTURE_KEY = "pendingCapture";
const DIVIDER = "---- additional context ----";

const URL_REGEX = /^https?:\/\/\S+$/i;
// Specific Chat message permalink has 3+ path segments after /dm/ or /room/.
const CHAT_MESSAGE_PERMALINK_REGEX =
  /^https:\/\/chat\.google\.com\/(dm|room)\/[^/?#]+\/[^/?#]+\/[^/?#]+/i;

// ---- Element references ----

const $options = document.getElementById("options-link");
const $healthDot = document.getElementById("health-dot");

const $sourceTitle = document.getElementById("source-title");
const $sourceFavicon = document.getElementById("source-favicon");
const FALLBACK_ICON = chrome.runtime.getURL("icons/icon-16.png");

function setFavicon(url) {
  if (!$sourceFavicon) return;
  $sourceFavicon.setAttribute("src", url || FALLBACK_ICON);
}

if ($sourceFavicon) {
  // If a favicon URL fails to load (404, network), fall back to the extension icon.
  $sourceFavicon.addEventListener("error", () => {
    if ($sourceFavicon.getAttribute("src") !== FALLBACK_ICON) {
      $sourceFavicon.setAttribute("src", FALLBACK_ICON);
    }
  });
}
const $sourceUrl = document.getElementById("source-url");
const $urlHint = document.getElementById("url-hint");
const $content = document.getElementById("content");
const $context = document.getElementById("context");
const $send = document.getElementById("send");
const $clear = document.getElementById("clear");
const $status = document.getElementById("status");

const $flagBrainDump = document.getElementById("flag-brain-dump");
const $flagJira = document.getElementById("flag-jira");
const $flagCodeResearch = document.getElementById("flag-code-research");
const $flagPrReview = document.getElementById("flag-pr-review");
const $flagSearchAround = document.getElementById("flag-search-around");
const $flagWebResearch = document.getElementById("flag-web-research");
const $flagMeeting = document.getElementById("flag-meeting");
const $flagReply = document.getElementById("flag-reply");
const $flagDecision = document.getElementById("flag-decision");
const $flagPerson = document.getElementById("flag-person");
const $flagAutoFile = document.getElementById("flag-auto-file");

const $epicBlock = document.getElementById("epic-block");
const $epicHint = document.getElementById("epic-hint");
const $meetingBlock = document.getElementById("meeting-block");
const $meetingAttendees = document.getElementById("meeting-attendees");
const $personBlock = document.getElementById("person-block");
const $personName = document.getElementById("person-name");
const $attachParent = document.getElementById("attach-parent");
const $sectionIdentity = document.getElementById("section-identity");
const $sectionDispatch = document.getElementById("section-dispatch");

const $draftNow = document.getElementById("draft-now");
const $draftResult = document.getElementById("draft-result");
const $draftText = document.getElementById("draft-text");
const $draftMeta = document.getElementById("draft-meta");
const $draftCopy = document.getElementById("draft-copy");
const $draftRedraft = document.getElementById("draft-redraft");
const $draftHide = document.getElementById("draft-hide");

let pending = null;
let urlAutoFilledFromClipboard = false;

// ---- Status ----

function setStatus(text, kind) {
  $status.textContent = text;
  $status.className = `status ${kind || "hint"}`;
}

// ---- URL hint ----

function describeUrl(url) {
  if (!url) return { text: "(no link)", kind: "" };
  if (CHAT_MESSAGE_PERMALINK_REGEX.test(url)) {
    return { text: "Google Chat message permalink (specific anchor)", kind: "ok" };
  }
  if (/^https:\/\/chat\.google\.com\//i.test(url)) {
    return { text: "Google Chat page (room-level, not message-specific)", kind: "warn" };
  }
  if (URL_REGEX.test(url)) return { text: "URL", kind: "ok" };
  return { text: "invalid URL", kind: "warn" };
}

function refreshUrlHint() {
  const url = $sourceUrl.value.trim();
  const { text, kind } = describeUrl(url);
  const prefix = urlAutoFilledFromClipboard ? "auto-filled from clipboard · " : "";
  $urlHint.textContent = prefix + text;
  $urlHint.className = `label-hint ${kind}`;
}

async function readClipboardUrl() {
  try {
    const text = (await navigator.clipboard.readText()).trim();
    if (text && URL_REGEX.test(text)) return text;
    return null;
  } catch (err) {
    console.warn("BriefCase: clipboard read failed", err);
    return null;
  }
}

// ---- Favicon helper ----

function faviconUrlFor(pageUrl) {
  if (!pageUrl) return "";
  try {
    const { origin } = new URL(pageUrl);
    // Chrome's built-in favicon service requires the "favicon" permission for
    // chrome-extension://...?pageUrl=... usage; use Google's S2 favicon as a
    // permission-free fallback. Good enough for the one-liner header.
    return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(origin)}&sz=32`;
  } catch (_e) {
    return "";
  }
}

// ---- Hydrate from background ----

function applyPending(data) {
  pending = data || null;

  if (!pending) {
    // Empty state — no source pre-fill, but the form is fully usable for
    // standalone captures via the panel.
    $sourceTitle.textContent = "BriefCase";
    $sourceTitle.title = "";
    setFavicon(null);
    return;
  }

  const titleText = pending.source_title || pending.source_url || "(no title)";
  $sourceTitle.textContent = titleText;
  $sourceTitle.title = titleText;
  setFavicon(faviconUrlFor(pending.source_url));
  $content.value = pending.initial_content || "";
  $sourceUrl.value = pending.source_url || "";
  refreshUrlHint();
}

async function hydrateFromStorage({ focusContext } = {}) {
  const data = await chrome.storage.session.get([PENDING_CAPTURE_KEY]);
  const next = data[PENDING_CAPTURE_KEY] || null;
  if (!next) {
    applyPending(null);
    return;
  }

  applyPending(next);

  // Clipboard URL takes precedence over the tab URL (handles "copy message
  // link" flow). Only attempt this on a fresh hydrate so we don't clobber
  // the user typing into the field.
  const clipboardUrl = await readClipboardUrl();
  if (clipboardUrl) {
    $sourceUrl.value = clipboardUrl;
    urlAutoFilledFromClipboard = true;
    refreshUrlHint();
  }

  // Clear the pending payload — we've absorbed it. Future tab-switches
  // shouldn't re-trigger the hydrate.
  await chrome.storage.session.remove(PENDING_CAPTURE_KEY);

  if (focusContext) $context.focus();
}

// ---- Form helpers ----

function isAttachedToParent() {
  return !!($attachParent && $attachParent.value);
}

function collectFlags() {
  const flags = {};
  const inherits = isAttachedToParent();
  // Identity and dispatch flags belong to the parent when attached.
  // Other checkboxes (context / actions) remain user-driven on the child.
  if (!inherits) {
    if ($flagBrainDump.checked) flags.is_brain_dump = true;
    if ($flagDecision.checked) flags.is_decision = true;
    if ($flagPerson.checked) flags.is_person = true;
    if ($flagAutoFile.checked) flags.auto_file = true;
    if ($flagPerson.checked) {
      const name = $personName.value.trim();
      if (name) flags.person_name = name;
    }
  }
  if ($flagJira.checked) flags.needs_jira = true;
  if ($flagCodeResearch.checked) flags.needs_code_research = true;
  if ($flagPrReview.checked) flags.needs_pr_review = true;
  if ($flagSearchAround.checked) flags.search_around = true;
  if ($flagWebResearch.checked) flags.needs_web_research = true;
  if ($flagMeeting.checked) flags.needs_meeting = true;
  if ($flagReply.checked) flags.needs_reply = true;
  const epic = $epicHint.value.trim();
  if (epic && $flagJira.checked) flags.epic_hint = epic;
  if ($flagMeeting.checked) {
    const raw = $meetingAttendees.value.trim();
    if (raw) {
      const attendees = raw
        .split(/[,\n]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      if (attendees.length) flags.meeting_attendees = attendees;
    }
  }
  return Object.keys(flags).length > 0 ? flags : null;
}

function syncEpicVisibility() {
  $epicBlock.classList.toggle("visible", $flagJira.checked);
}
function syncMeetingVisibility() {
  $meetingBlock.classList.toggle("visible", $flagMeeting.checked);
}
function syncPersonVisibility() {
  $personBlock.classList.toggle("visible", $flagPerson.checked);
}

function buildClipFromForm() {
  const captured = $content.value.trimEnd();
  const context = $context.value.trim();
  const urlValue = $sourceUrl.value.trim();

  const combined = context
    ? `${captured}\n\n${DIVIDER}\n${context}`
    : captured;

  const baseClip = (pending && pending.baseClip) || {
    source: "web_clip",
    content: "",
    source_url: null,
    title: null,
    metadata: {},
  };
  const baseMetadata = baseClip.metadata || {};
  const captureType = (pending && pending.capture_type) || "panel_standalone";
  const metadata = {
    ...baseMetadata,
    capture_type: captureType,
  };
  if (context) metadata.user_context = context;
  if (urlAutoFilledFromClipboard && urlValue) {
    metadata.url_source = "clipboard";
  } else if (urlValue && pending && urlValue !== pending.source_url) {
    metadata.url_source = "user_edited";
  }

  const clip = {
    ...baseClip,
    content: combined,
    source_url: urlValue || null,
    metadata,
    flags: collectFlags(),
  };
  const parentId = $attachParent && parseInt($attachParent.value, 10);
  if (parentId) clip.attach_to_id = parentId;
  return clip;
}

// ---- Attach-to-parent dropdown ----

function formatAge(isoTimestamp) {
  if (!isoTimestamp) return "";
  const then = new Date(isoTimestamp);
  if (Number.isNaN(then.getTime())) return "";
  const seconds = Math.max(0, Math.floor((Date.now() - then.getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

async function loadAttachOptions() {
  if (!$attachParent) return;
  // Reset to placeholder before repopulating (panel may refresh repeatedly).
  while ($attachParent.options.length > 1) {
    $attachParent.remove(1);
  }
  try {
    const resp = await chrome.runtime.sendMessage({ type: "LIST_PENDING_TRIAGE", limit: 10 });
    if (!resp || !resp.ok || !Array.isArray(resp.data)) return;
    for (const item of resp.data) {
      const opt = document.createElement("option");
      opt.value = String(item.id);
      const label = item.title || item.content_preview || `#${item.id}`;
      const age = formatAge(item.captured_at);
      opt.textContent = age ? `#${item.id} · ${label} (${age})` : `#${item.id} · ${label}`;
      $attachParent.appendChild(opt);
    }
  } catch (err) {
    console.warn("BriefCase: loadAttachOptions failed", err);
  }
}

function syncAttachInheritance() {
  if (!$attachParent || !$sectionIdentity || !$sectionDispatch) return;
  if (isAttachedToParent()) {
    $sectionIdentity.classList.add("inherited-from-parent");
    $sectionDispatch.classList.add("inherited-from-parent");
  } else {
    $sectionIdentity.classList.remove("inherited-from-parent");
    $sectionDispatch.classList.remove("inherited-from-parent");
  }
}

// ---- Send / clear ----

function resetForm() {
  pending = null;
  urlAutoFilledFromClipboard = false;
  $content.value = "";
  $context.value = "";
  $sourceUrl.value = "";
  $sourceTitle.textContent = "BriefCase";
  $sourceTitle.title = "";
  setFavicon(null);
  [
    $flagBrainDump, $flagDecision, $flagPerson, $flagAutoFile,
    $flagJira, $flagCodeResearch, $flagPrReview, $flagSearchAround,
    $flagWebResearch, $flagMeeting, $flagReply,
  ].forEach((el) => { if (el) el.checked = false; });
  $epicHint.value = "";
  $meetingAttendees.value = "";
  $personName.value = "";
  if ($attachParent) $attachParent.value = "";
  syncEpicVisibility();
  syncMeetingVisibility();
  syncPersonVisibility();
  syncAttachInheritance();
  refreshUrlHint();
  hideDraft();
  setStatus("", "hint");
}

function send() {
  const clip = buildClipFromForm();
  if (!clip.content) {
    setStatus("Nothing to send — content is empty.", "err");
    return;
  }

  $send.disabled = true;
  setStatus("Sending...", "hint");

  chrome.runtime.sendMessage({ type: "SEND_CLIP", clip }, async (resp) => {
    $send.disabled = false;
    if (!resp) {
      setStatus("No response from service worker.", "err");
      return;
    }
    if (!resp.ok) {
      setStatus(resp.error || "Failed to send.", "err");
      return;
    }
    setStatus(`Queued as #${resp.data.triage_item_id}.`, "ok");
    // Reset so the panel is ready for the next capture, but leave the status
    // visible briefly so the user sees the confirmation.
    setTimeout(() => {
      resetForm();
      loadAttachOptions();
      refreshHealth();
      setStatus(`Queued as #${resp.data.triage_item_id}.`, "ok");
    }, 400);
  });
}

// ---- Draft now ----

function draftNow() {
  const captured = $content.value.trim();
  if (!captured) {
    setStatus("Nothing to draft from - the captured content is empty.", "err");
    return;
  }
  const context = $context.value.trim();

  $draftNow.disabled = true;
  $send.disabled = true;
  setStatus("Drafting via claude -p... (5-15s)", "hint");

  chrome.runtime.sendMessage(
    {
      type: "DRAFT_REPLY",
      payload: {
        content: captured,
        context: context || null,
        tone: "informal",
        mode: "reply",
        destination: "google-chat",
      },
    },
    (resp) => {
      $draftNow.disabled = false;
      $send.disabled = false;
      if (!resp) {
        setStatus("No response from service worker.", "err");
        return;
      }
      if (!resp.ok) {
        setStatus(resp.error || "Draft failed.", "err");
        return;
      }
      const { draft, elapsed_ms } = resp.data;
      $draftText.value = draft;
      $draftMeta.textContent = `${(elapsed_ms / 1000).toFixed(1)}s · ${draft.length} chars`;
      $draftResult.hidden = false;
      setStatus("", "hint");
      $draftText.focus();
      $draftText.select();
    }
  );
}

async function copyDraftToClipboard() {
  const text = $draftText.value;
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    setStatus("Draft copied to clipboard.", "ok");
  } catch (err) {
    setStatus(`Couldn't copy: ${err.message || err}`, "err");
  }
}

function hideDraft() {
  $draftResult.hidden = true;
  $draftText.value = "";
}

// ---- Health widget ----

function setHealthDot(state, tooltip) {
  $healthDot.classList.remove("ok", "err");
  if (state === "ok") $healthDot.classList.add("ok");
  else if (state === "err") $healthDot.classList.add("err");
  $healthDot.title = tooltip;
}

function refreshHealth() {
  setHealthDot(null, "Checking sidecar...");
  chrome.runtime.sendMessage({ type: "HEALTH_CHECK" }, (resp) => {
    if (!resp) {
      setHealthDot("err", "No response from service worker.");
      return;
    }
    if (resp.ok) {
      const { version, pending_count } = resp.data;
      setHealthDot("ok", `Sidecar ${version} · ${pending_count} pending`);
    } else {
      setHealthDot("err", `Can't reach sidecar${resp.error ? " · " + resp.error : ""}`);
    }
  });
}

// ---- Wire up ----

$options.addEventListener("click", (e) => {
  e.preventDefault();
  chrome.runtime.openOptionsPage();
});

$send.addEventListener("click", send);
$clear.addEventListener("click", () => {
  resetForm();
  $content.focus();
});
$draftNow.addEventListener("click", draftNow);
$draftCopy.addEventListener("click", copyDraftToClipboard);
$draftRedraft.addEventListener("click", () => {
  hideDraft();
  draftNow();
});
$draftHide.addEventListener("click", hideDraft);

$sourceUrl.addEventListener("input", () => {
  urlAutoFilledFromClipboard = false;
  refreshUrlHint();
});

$flagJira.addEventListener("change", () => {
  syncEpicVisibility();
  if ($flagJira.checked) $epicHint.focus();
});
$flagMeeting.addEventListener("change", () => {
  syncMeetingVisibility();
  if ($flagMeeting.checked) $meetingAttendees.focus();
});
$flagPerson.addEventListener("change", () => {
  syncPersonVisibility();
  if ($flagPerson.checked) $personName.focus();
});

if ($attachParent) {
  $attachParent.addEventListener("change", syncAttachInheritance);
}

document.addEventListener("keydown", (e) => {
  const isCmd = e.metaKey || e.ctrlKey;
  if (isCmd && e.key === "Enter") {
    e.preventDefault();
    send();
  } else if (isCmd && (e.key === "d" || e.key === "D")) {
    e.preventDefault();
    draftNow();
  } else if (e.key === "Escape") {
    // In a popup window, Esc closed it. In a persistent panel we just blur
    // focus — there's no panel to close, and chrome.sidePanel.close() isn't
    // available on stable everywhere.
    if (document.activeElement && document.activeElement.blur) {
      document.activeElement.blur();
    }
  }
});

// Background pushes us a hydrate signal after stashing a pending capture
// from the user-gesture path (right-click, hotkey, action click). Re-read
// session storage when that fires.
chrome.runtime.onMessage.addListener((msg) => {
  if (msg?.type === "HYDRATE_PENDING") {
    hydrateFromStorage({ focusContext: true });
  }
});

// Storage change is a secondary path — if anything stashes a capture while
// the panel is already open, pick it up.
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "session" && changes[PENDING_CAPTURE_KEY]?.newValue) {
    hydrateFromStorage({ focusContext: true });
  }
});

// Initial load.
refreshHealth();
loadAttachOptions();
hydrateFromStorage({ focusContext: false });
