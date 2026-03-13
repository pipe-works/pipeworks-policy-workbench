import { THEME_STORAGE_KEY } from "./constants.js";
import { dom } from "./dom.js";
import { configureRuntime } from "./runtime.js";
import { configureInventory } from "./inventory.js";
import { configureTree } from "./tree.js";
import { configureHash } from "./hash.js";
import { configureValidation } from "./validation.js";
import { configureSyncCompare } from "./sync_compare.js";
import { configureSyncPlan, renderUnchangedBreakdown } from "./sync_plan.js";
import { configureEditorActions } from "./editor_actions.js";
import { configureRuntimeSession } from "./runtime_session.js";
import { configureBoot, initializeWorkbench } from "./boot.js";

function setStatus(message) {
  dom.statusText.textContent = message;
}

function formatLocalDateTime(dateValue) {
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(dateValue);
}

function wireThemeToggle() {
  const button = dom.themeToggle;
  if (!button) {
    return;
  }

  const applyTheme = (theme) => {
    const normalizedTheme = theme === "light" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", normalizedTheme);
    button.textContent = normalizedTheme === "light" ? "\u263E Dark" : "\u2600 Light";

    try {
      localStorage.setItem(THEME_STORAGE_KEY, normalizedTheme);
    } catch {
      // Theme persistence is optional; UI still works without storage access.
    }
  };

  let savedTheme = "dark";
  try {
    savedTheme = localStorage.getItem(THEME_STORAGE_KEY) || "dark";
  } catch {
    // Fall back to default theme when storage is unavailable.
  }
  applyTheme(savedTheme);

  button.addEventListener("click", () => {
    const currentTheme = document.documentElement.getAttribute("data-theme") || "dark";
    applyTheme(currentTheme === "dark" ? "light" : "dark");
  });
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {
      // Use fallback detail.
    }
    throw new Error(detail);
  }

  return response.json();
}

configureRuntime({ fetchJson, setStatus });
configureRuntimeSession({ fetchJson, setStatus });
configureInventory({ fetchJson, setStatus });
configureTree({ fetchJson, setStatus });
configureSyncCompare({ fetchJson, setStatus });
configureSyncPlan({
  fetchJson,
  setStatus,
  formatLocalDateTime,
});
configureEditorActions({ fetchJson, setStatus });
configureHash({
  fetchJson,
  setStatus,
  formatLocalDateTime,
  renderUnchangedBreakdown,
});
configureValidation({ fetchJson, setStatus });
configureBoot({ setStatus });

async function init() {
  wireThemeToggle();
  await initializeWorkbench();
}

init();
