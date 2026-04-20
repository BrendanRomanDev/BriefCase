const $health = document.getElementById("health");
const $options = document.getElementById("options-link");

$options.addEventListener("click", (e) => {
  e.preventDefault();
  chrome.runtime.openOptionsPage();
});

chrome.runtime.sendMessage({ type: "HEALTH_CHECK" }, (resp) => {
  if (!resp) {
    $health.textContent = "No response from service worker.";
    $health.classList.add("err");
    return;
  }
  if (resp.ok) {
    const { version, pending_count } = resp.data;
    $health.innerHTML = `<span class="ok">Sidecar ${version}</span><br>${pending_count} pending in queue`;
  } else {
    $health.innerHTML = `<span class="err">Can't reach sidecar</span><br>${resp.error}`;
  }
});
