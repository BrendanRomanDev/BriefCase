// BriefCase compose popup: edit the captured content and add extra context.

const PENDING_CAPTURE_KEY = "pendingCapture";
const DIVIDER = "---- additional context ----";

const $sourceTitle = document.getElementById("source-title");
const $sourceUrl = document.getElementById("source-url");
const $content = document.getElementById("content");
const $context = document.getElementById("context");
const $send = document.getElementById("send");
const $cancel = document.getElementById("cancel");
const $status = document.getElementById("status");

let pending = null;

function setStatus(text, kind) {
  $status.textContent = text;
  $status.className = `status ${kind || "hint"}`;
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
  $sourceUrl.textContent = pending.source_url || "(no URL)";
  $content.value = pending.initial_content || "";
  $context.focus();
}

function buildClipFromForm() {
  const captured = $content.value.trimEnd();
  const context = $context.value.trim();

  const combined = context
    ? `${captured}\n\n${DIVIDER}\n${context}`
    : captured;

  const baseMetadata = (pending.baseClip && pending.baseClip.metadata) || {};
  const metadata = {
    ...baseMetadata,
    capture_type: pending.capture_type,
  };
  if (context) metadata.user_context = context;

  return {
    ...pending.baseClip,
    content: combined,
    metadata,
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

  chrome.runtime.sendMessage({ type: "SEND_WITH_CONTEXT", clip }, async (resp) => {
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

$send.addEventListener("click", send);
$cancel.addEventListener("click", cancel);

document.addEventListener("keydown", (e) => {
  const isCmdEnter = (e.metaKey || e.ctrlKey) && e.key === "Enter";
  if (isCmdEnter) {
    e.preventDefault();
    send();
  } else if (e.key === "Escape") {
    e.preventDefault();
    cancel();
  }
});

load();
