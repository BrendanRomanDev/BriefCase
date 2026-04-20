// BriefCase options page logic.

const DEFAULT_SIDECAR_URL = "http://127.0.0.1:8989";

const $url = document.getElementById("sidecarUrl");
const $token = document.getElementById("authToken");
const $save = document.getElementById("save");
const $test = document.getElementById("test");
const $status = document.getElementById("status");

function setStatus(text, kind) {
  $status.textContent = text;
  $status.className = `status ${kind || "info"}`;
}

async function load() {
  const { sidecarUrl, authToken } = await chrome.storage.sync.get([
    "sidecarUrl",
    "authToken",
  ]);
  $url.value = sidecarUrl || DEFAULT_SIDECAR_URL;
  $token.value = authToken || "";
}

async function save() {
  const sidecarUrl = $url.value.trim() || DEFAULT_SIDECAR_URL;
  const authToken = $token.value.trim();
  if (!authToken) {
    setStatus("Auth token is required.", "err");
    return;
  }
  await chrome.storage.sync.set({ sidecarUrl, authToken });
  setStatus("Saved.", "ok");
}

async function testConnection() {
  setStatus("Testing...", "info");
  const sidecarUrl = $url.value.trim() || DEFAULT_SIDECAR_URL;
  try {
    const r = await fetch(`${sidecarUrl}/health`);
    if (!r.ok) {
      setStatus(`Health check HTTP ${r.status}`, "err");
      return;
    }
    const data = await r.json();
    setStatus(
      `Sidecar ${data.version} — ${data.pending_count} pending in queue.`,
      "ok"
    );
  } catch (err) {
    setStatus(
      `Can't reach sidecar at ${sidecarUrl}: ${err.message || err}`,
      "err"
    );
  }
}

$save.addEventListener("click", save);
$test.addEventListener("click", testConnection);
load();
