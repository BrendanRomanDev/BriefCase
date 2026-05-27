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
const $flagCodeResearch = document.getElementById("flag-code-research");
const $flagPrReview = document.getElementById("flag-pr-review");
const $flagSearchAround = document.getElementById("flag-search-around");
const $flagWebResearch = document.getElementById("flag-web-research");
const $flagMeeting = document.getElementById("flag-meeting");
const $flagReply = document.getElementById("flag-reply");
const $flagDecision = document.getElementById("flag-decision");
const $flagPerson = document.getElementById("flag-person");
const $flagKudos = document.getElementById("flag-kudos");
const $flagAutoFile = document.getElementById("flag-auto-file");
const $kudosBanner = document.getElementById("kudos-banner");
const $kudosRecipientBlock = document.getElementById("kudos-recipient-block");
const $kudosRecipient = document.getElementById("kudos-recipient");
const $sourceTitleBlock = document.getElementById("source-title-block");
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

function applyKudosMode() {
  // Pre-flag the capture as kudos, swap the page-source banner for the
  // kudos banner, reveal the recipient field, and switch the textarea
  // labels/placeholders to kudos-shaped prompts.
  if ($sourceTitleBlock) $sourceTitleBlock.style.display = "none";
  if ($kudosBanner) $kudosBanner.style.display = "";
  if ($kudosRecipientBlock) $kudosRecipientBlock.style.display = "";
  if ($flagKudos) $flagKudos.checked = true;

  const contentLabel = document.querySelector(".content-block .field-label");
  if (contentLabel) contentLabel.textContent = "What did they do? (the kudos-worthy thing)";
  if ($content) {
    $content.placeholder = "e.g. Randall unblocked the PMT data model thing — stayed late debugging the override resolver until it lit up green.";
  }
  const contextLabel = document.querySelector(".context-block .field-label");
  if (contextLabel) contextLabel.textContent = "Any extra context (optional — tone, where to post, related work)";
  if ($context) {
    $context.placeholder = "e.g. wanted to call this out in the #kudos channel; bonus points if you can tie it to the PMT rebuild push.";
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

  if (pending.kudos_mode) {
    applyKudosMode();
  } else {
    $sourceTitle.textContent = pending.source_title || "(no title)";
  }
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
  if (pending.kudos_mode && $kudosRecipient) {
    $kudosRecipient.focus();
  } else {
    $context.focus();
  }
}

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
    if ($flagKudos && $flagKudos.checked) flags.kudos = true;
    if ($flagAutoFile.checked) flags.auto_file = true;
    if ($flagPerson.checked) {
      const name = $personName.value.trim();
      if (name) flags.person_name = name;
    }
    if ($flagKudos && $flagKudos.checked && $kudosRecipient) {
      const recipient = $kudosRecipient.value.trim();
      if (recipient) flags.kudos_recipient = recipient;
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

function syncPersonVisibility() {
  if ($flagPerson.checked) {
    $personBlock.classList.add("visible");
  } else {
    $personBlock.classList.remove("visible");
  }
}

function syncKudosVisibility() {
  if (!$flagKudos || !$kudosRecipientBlock) return;
  // In kudos-mode launches the recipient field is already shown via
  // applyKudosMode and the checkbox is pre-checked. From a regular capture,
  // toggling the kudos checkbox reveals/hides the recipient field too.
  $kudosRecipientBlock.style.display = $flagKudos.checked ? "" : "none";
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

  const clip = {
    ...pending.baseClip,
    content: combined,
    source_url: urlValue || null,
    metadata,
    flags: collectFlags(),
  };
  const parentId = $attachParent && parseInt($attachParent.value, 10);
  if (parentId) clip.attach_to_id = parentId;
  return clip;
}

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
        // Extension captures are almost always Google Chat or web clips.
        // Default to google-chat so markdown chars don't paste as literal noise.
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

$flagPerson.addEventListener("change", () => {
  syncPersonVisibility();
  if ($flagPerson.checked) $personName.focus();
});

if ($flagKudos) {
  $flagKudos.addEventListener("change", () => {
    syncKudosVisibility();
    if ($flagKudos.checked && $kudosRecipient) $kudosRecipient.focus();
  });
}

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
    e.preventDefault();
    cancel();
  }
});

load();
loadAttachOptions();
