// BriefCase theme system.
//
// Themes are defined in themes.css as CSS variable sets gated by
// [data-theme="..."]. This module:
//   - exposes the registry of available themes
//   - reads the user's saved theme from chrome.storage.sync (canonical)
//     plus localStorage (synchronous cache to prevent FOUC)
//   - applies the theme to <html data-theme="..."> on page load
//
// All extension HTML pages should include themes.css and theme.js.

const STORAGE_KEY = "theme";
const LS_CACHE_KEY = "briefcase.theme.cache";
const DEFAULT_THEME = "light";

// Display order for the options selector. Group light/dark intentionally.
const THEMES = [
  { id: "light",            label: "Light",              kind: "light"  },
  { id: "dark",             label: "Dark",               kind: "dark"   },
  { id: "system",           label: "System (follow OS)", kind: "auto"   },
  { id: "sepia",            label: "Sepia",              kind: "light"  },
  { id: "solarized-light",  label: "Solarized Light",    kind: "light"  },
  { id: "catppuccin-latte", label: "Catppuccin Latte",   kind: "light"  },
  { id: "solarized-dark",   label: "Solarized Dark",     kind: "dark"   },
  { id: "nord",             label: "Nord",               kind: "dark"   },
  { id: "dracula",          label: "Dracula",            kind: "dark"   },
  { id: "gruvbox-dark",     label: "Gruvbox Dark",       kind: "dark"   },
  { id: "tokyo-night",      label: "Tokyo Night",        kind: "dark"   },
  { id: "catppuccin-mocha", label: "Catppuccin Mocha",   kind: "dark"   },
  { id: "high-contrast",    label: "High Contrast",      kind: "dark"   },
];

const VALID_IDS = new Set(THEMES.map((t) => t.id));

function applyThemeId(themeId) {
  const id = VALID_IDS.has(themeId) ? themeId : DEFAULT_THEME;
  document.documentElement.setAttribute("data-theme", id);
  return id;
}

// Synchronous early apply: reads localStorage cache to avoid FOUC.
// Called immediately on script load.
function applyCachedTheme() {
  try {
    const cached = localStorage.getItem(LS_CACHE_KEY);
    if (cached) applyThemeId(cached);
    else applyThemeId(DEFAULT_THEME);
  } catch (_e) {
    applyThemeId(DEFAULT_THEME);
  }
}

// Async: reads canonical chrome.storage.sync and overrides if different.
// Also refreshes the localStorage cache.
async function syncTheme() {
  try {
    const stored = await chrome.storage.sync.get([STORAGE_KEY]);
    const themeId = stored[STORAGE_KEY] || DEFAULT_THEME;
    applyThemeId(themeId);
    try {
      localStorage.setItem(LS_CACHE_KEY, themeId);
    } catch (_e) {}
    return themeId;
  } catch (err) {
    console.warn("BriefCase: failed to read theme from storage", err);
    return DEFAULT_THEME;
  }
}

async function setTheme(themeId) {
  const id = applyThemeId(themeId);
  await chrome.storage.sync.set({ [STORAGE_KEY]: id });
  try {
    localStorage.setItem(LS_CACHE_KEY, id);
  } catch (_e) {}
  return id;
}

async function getCurrentTheme() {
  const stored = await chrome.storage.sync.get([STORAGE_KEY]);
  return stored[STORAGE_KEY] || DEFAULT_THEME;
}

// Apply the cached theme synchronously the moment this script loads,
// then async-reconcile with canonical storage.
applyCachedTheme();
syncTheme();

// React to changes from other extension pages (e.g. options page changing
// the theme while compose popup is open).
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "sync") return;
  if (changes[STORAGE_KEY]) {
    const newId = changes[STORAGE_KEY].newValue || DEFAULT_THEME;
    applyThemeId(newId);
    try {
      localStorage.setItem(LS_CACHE_KEY, newId);
    } catch (_e) {}
  }
});

// Expose a tiny API for the options page.
window.BriefCaseTheme = {
  THEMES,
  setTheme,
  getCurrentTheme,
  DEFAULT_THEME,
};
