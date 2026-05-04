// BriefCase compose popup: edit the captured content, override the source URL
// (e.g. paste a Google Chat message permalink), and add extra context before
// sending to the sidecar.

const PENDING_CAPTURE_KEY = "pendingCapture";
const DIVIDER = "---- additional context ----";

const URL_REGEX = /^https?:\/\/\S+$/i;
// Specific Chat message permalink has 3+ path segments after /dm/ or /room/.
const CHAT_MESSAGE_PERMALINK_REGEX =
  /^https:\/\/chat\.google\.com\/(dm|room)\/[^/?#]+\/[^/?#]+\/[^/?#]+/i;

const $sourceTitle = document.getElementById("source-title");
const $sourceUrl = document.getElementById("source-url");
const $urlHint = document.getElementById("url-hint");
const $content = document.getElementById("content");
const $context = document.getElementById("context");
const $send = document.getElementById("send");
const $cancel = document.getElementById("cancel");
const $status = document.getElementById("status");
const $flagBrainDump = document.getElementById("flag-brain-dump");
const $flagJira = document.getElementById("flag-jira");
const $flagCodeReview = document.getElementById("flag-code-review");
const $flagSearchAround = document.getElementById("flag-search-around");
const $flagMeeting = document.getElementById("flag-meeting");
const $flagReply = document.getElementById("flag-reply");
const $flagDecision = document.getElementById("flag-decision");
const $epicBlock = document.getElementById("epic-block");
const $epicHint = document.getElementById("epic-hint");
const $meetingBlock = document.getElementById("meeting-block");
const $meetingAttendees = document.getElementById("meeting-attendees");

const $draftNow = document.getElementById("draft-now");
const $draftResult = document.getElementById("draft-result");
const $draftText = document.getElementById("draft-text");
const $draftMeta = document.getElementById("draft-meta");
const $draftCopy = document.getElementById("draft-copy");
const $draftRedraft = document.getElementById("draft-redraft");
const $draftHide = document.getElementById("draft-hide");

let pending = null;
let urlAutoFilledFromClipboard = false;

function setStatus(text, kind) {
  $status.textContent = text;
  $status.className = `status ${kind || "hint"}`;
}

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

async function load() {
  const data = await chrome.storage.session.get([PENDING_CAPTURE_KEY]);
  pending = data[PENDING_CAPTURE_KEY] || null;

  if (!pending) {
    setStatus("No pending capture found. Close this window and try again.", "err");
    $send.disabled = true;
    return;
  }

  $sourceTitle.textContent = pending.source_title || "(no title)";
  $content.value = pending.initial_content || "";

  // Precedence for source URL:
  //   1. Clipboard, if it's a URL (handles "copy message link" flow)
  //   2. pending.source_url (page URL from the active tab)
  const clipboardUrl = await readClipboardUrl();
  if (clipboardUrl) {
    $sourceUrl.value = clipboardUrl;
    urlAutoFilledFromClipboard = true;
  } else {
    $sourceUrl.value = pending.source_url || "";
  }

  refreshUrlHint();
  $context.focus();
}

function collectFlags() {
  const flags = {};
  if ($flagBrainDump.checked) flags.is_brain_dump = true;
  if ($flagJira.checked) flags.needs_jira = true;
  if ($flagCodeReview.checked) flags.needs_code_review = true;
  if ($flagSearchAround.checked) flags.search_around = true;
  if ($flagMeeting.checked) flags.needs_meeting = true;
  if ($flagReply.checked) flags.needs_reply = true;
  if ($flagDecision.checked) flags.is_decision = true;
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
  if ($flagJira.checked) {
    $epicBlock.classList.add("visible");
  } else {
    $epicBlock.classList.remove("visible");
  }
}

function syncMeetingVisibility() {
  if ($flagMeeting.checked) {
    $meetingBlock.classList.add("visible");
  } else {
    $meetingBlock.classList.remove("visible");
  }
}

function buildClipFromForm() {
  const captured = $content.value.trimEnd();
  const context = $context.value.trim();
  const urlValue = $sourceUrl.value.trim();

  const combined = context
    ? `${captured}\n\n${DIVIDER}\n${context}`
    : captured;

  const baseMetadata = (pending.baseClip && pending.baseClip.metadata) || {};
  const metadata = {
    ...baseMetadata,
    capture_type: pending.capture_type,
  };
  if (context) metadata.user_context = context;
  if (urlAutoFilledFromClipboard && urlValue) {
    metadata.url_source = "clipboard";
  } else if (urlValue && urlValue !== pending.source_url) {
    metadata.url_source = "user_edited";
  }

  return {
    ...pending.baseClip,
    content: combined,
    source_url: urlValue || null,
    metadata,
    flags: collectFlags(),
  };
}

async function send() {
  if (!pending) return;
  const clip = buildClipFromForm();
  if (!clip.content) {
    setStatus("Nothing to send — content is empty.", "err");
    return;
  }

  $send.disabled = true;
  $cancel.disabled = true;
  setStatus("Sending...", "hint");

  chrome.runtime.sendMessage({ type: "SEND_CLIP", clip }, async (resp) => {
    if (!resp) {
      setStatus("No response from service worker.", "err");
      $send.disabled = false;
      $cancel.disabled = false;
      return;
    }
    if (!resp.ok) {
      setStatus(resp.error || "Failed to send.", "err");
      $send.disabled = false;
      $cancel.disabled = false;
      return;
    }
    setStatus(`Queued as #${resp.data.triage_item_id}.`, "ok");
    await chrome.storage.session.remove(PENDING_CAPTURE_KEY);
    setTimeout(() => window.close(), 350);
  });
}

async function cancel() {
  await chrome.storage.session.remove(PENDING_CAPTURE_KEY);
  window.close();
}

// ---- Draft now ----

async function draftNow() {
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

$send.addEventListener("click", send);
$cancel.addEventListener("click", cancel);
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

document.addEventListener("keydown", (e) => {
  const isCmd = e.metaKey || e.ctrlKey;
  if (isCmd && e.key === "Enter") {
    e.preventDefault();
    send();
  } else if (isCmd && (e.key === "d" || e.key === "D")) {
    e.preventDefault();
    draftNow();
  } else if (e.key === "Escape") {
    e.preventDefault();
    cancel();
  }
});

load();
