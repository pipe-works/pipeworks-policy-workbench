import { dom } from "./dom.js";
import { state } from "./state.js";

let _fetchJson = null;
let _setStatus = null;

export function configureRuntime({ fetchJson, setStatus }) {
  _fetchJson = fetchJson;
  _setStatus = setStatus;
}

function requireRuntimeDeps() {
  if (!_fetchJson || !_setStatus) {
    throw new Error("Runtime helpers are not configured.");
  }
}

export function setRuntimeSessionId(sessionId) {
  state.runtimeSessionId = String(sessionId || "").trim();
}

export function sessionScopedUrl(urlPath) {
  const sessionId = (state.runtimeSessionId || "").trim();
  if (!sessionId) {
    return urlPath;
  }

  const url = new URL(urlPath, window.location.origin);
  url.searchParams.set("session_id", sessionId);
  const queryText = url.searchParams.toString();
  return queryText ? `${url.pathname}?${queryText}` : url.pathname;
}

function activeRuntimeModeOption() {
  if (!state.runtimeMode) {
    return null;
  }
  return (
    state.runtimeModeOptionsByKey.get(state.runtimeMode.mode_key)
    || (state.runtimeMode.options || []).find(
      (candidate) => candidate.mode_key === state.runtimeMode.mode_key
    )
    || null
  );
}

function activeRuntimeServerUrl() {
  return (state.runtimeMode?.active_server_url || "").trim();
}

export function runtimeModeLabel() {
  if (!state.runtimeMode) {
    return "Unknown";
  }
  const option = activeRuntimeModeOption();
  return option?.label || state.runtimeMode.mode_key;
}

export function runtimeAuthStatus() {
  return String(state.runtimeAuth?.status || "");
}

export function isServerAuthorized() {
  return Boolean(state.runtimeAuth?.access_granted);
}

export function isRuntimeSessionAuthorized() {
  return isServerAuthorized() && Boolean((state.runtimeSessionId || "").trim());
}

function setRuntimeModeBadge() {
  if (!dom.runtimeModeBadge) {
    return;
  }

  const label = runtimeModeLabel();
  dom.runtimeModeBadge.classList.remove("badge--muted", "badge--active", "badge--info");
  if (state.runtimeMode?.mode_key === "server_dev") {
    dom.runtimeModeBadge.classList.add("badge--active");
  } else {
    dom.runtimeModeBadge.classList.add("badge--info");
  }
  dom.runtimeModeBadge.textContent = `${label} · Server API`;
}

function setRuntimeAuthIndicators() {
  if (!dom.runtimeAuthBadge) {
    return;
  }

  dom.runtimeAuthBadge.classList.remove(
    "badge--muted",
    "badge--active",
    "badge--info",
    "badge--warn",
    "badge--err"
  );

  const authStatus = runtimeAuthStatus();
  if (!authStatus) {
    dom.runtimeAuthBadge.classList.add("badge--muted");
    dom.runtimeAuthBadge.textContent = "Auth Pending";
  } else if (authStatus === "authorized") {
    dom.runtimeAuthBadge.classList.add("badge--active");
    dom.runtimeAuthBadge.textContent = "Auth OK";
  } else if (authStatus === "missing_session") {
    dom.runtimeAuthBadge.classList.add("badge--warn");
    dom.runtimeAuthBadge.textContent = "Session Missing";
  } else if (authStatus === "forbidden") {
    dom.runtimeAuthBadge.classList.add("badge--err");
    dom.runtimeAuthBadge.textContent = "Role Denied";
  } else if (authStatus === "unauthenticated") {
    dom.runtimeAuthBadge.classList.add("badge--warn");
    dom.runtimeAuthBadge.textContent = "Session Invalid";
  } else {
    dom.runtimeAuthBadge.classList.add("badge--err");
    dom.runtimeAuthBadge.textContent = "Auth Error";
  }
}

export function setSourceBadges() {
  const modeLabel = runtimeModeLabel();
  const activeUrl = activeRuntimeServerUrl();

  const serverBadgeText = `${modeLabel}${activeUrl ? ` · ${activeUrl}` : ""}`;

  if (dom.inventorySourceBadge) {
    const canReadServer = isServerAuthorized();
    const lockedBadgeClass = "badge badge--warn";
    dom.inventorySourceBadge.className = canReadServer ? "badge badge--info" : lockedBadgeClass;
    dom.inventorySourceBadge.textContent = canReadServer ? serverBadgeText : "Server locked";
    dom.inventorySourceBadge.title = canReadServer
      ? "Policy inventory and object detail are read from mud-server policy APIs."
      : "Inventory requires an admin/superuser mud-server session.";
  }

  if (dom.activationSourceBadge) {
    const canReadServer = isServerAuthorized();
    const lockedBadgeClass = "badge badge--warn";
    dom.activationSourceBadge.className = canReadServer ? "badge badge--info" : lockedBadgeClass;
    dom.activationSourceBadge.textContent = canReadServer ? serverBadgeText : "Server locked";
    dom.activationSourceBadge.title = canReadServer
      ? "Activation mapping is read from mud-server policy activation APIs."
      : "Activation mapping requires an admin/superuser mud-server session.";
  }

  if (!dom.editorSourceBadge) {
    return;
  }
  if (state.selectedPolicyRecord) {
    dom.editorSourceBadge.className = "badge badge--info";
    dom.editorSourceBadge.textContent = "Server API";
    dom.editorSourceBadge.title = "Editor content loaded from mud-server policy object content.";
    return;
  }
  dom.editorSourceBadge.className = "badge badge--muted";
  dom.editorSourceBadge.textContent = "No selection";
  dom.editorSourceBadge.title = "Select a policy object from inventory.";
}

export function updateStatusSourceLine() {
  if (!dom.statusSource) {
    return;
  }
  const modeLabel = runtimeModeLabel();
  const authStatus = runtimeAuthStatus() || "pending";
  dom.statusSource.textContent = `mode: ${modeLabel} · auth: ${authStatus}`;
  dom.statusSource.title = `mode=${modeLabel}\nauth=${authStatus}`;
}

export function applyRuntimeModeControls() {
  if (!dom.runtimeModeSelect || !state.runtimeMode) {
    return;
  }

  state.runtimeModeOptionsByKey = new Map();
  dom.runtimeModeSelect.innerHTML = "";
  for (const option of state.runtimeMode.options || []) {
    state.runtimeModeOptionsByKey.set(option.mode_key, option);
    const optionElement = document.createElement("option");
    optionElement.value = option.mode_key;
    optionElement.textContent = option.label;
    dom.runtimeModeSelect.appendChild(optionElement);
  }

  if (dom.runtimeModeSelect.querySelector(`option[value="${state.runtimeMode.mode_key}"]`)) {
    dom.runtimeModeSelect.value = state.runtimeMode.mode_key;
  }

  const activeOption = activeRuntimeModeOption();
  const editableServerUrl = Boolean(activeOption?.url_editable);
  const activeServerUrl = activeRuntimeServerUrl();
  const defaultServerUrl = (activeOption?.default_server_url || "").trim();
  const usernameValue = (dom.runtimeLoginUsername?.value || "").trim();
  const passwordValue = (dom.runtimeLoginPassword?.value || "").trim();

  if (dom.runtimeModeUrl) {
    dom.runtimeModeUrl.classList.toggle("hidden", !editableServerUrl);
    dom.runtimeModeUrl.value = activeServerUrl || defaultServerUrl;
  }
  if (dom.runtimeModeApply) {
    dom.runtimeModeApply.classList.toggle("hidden", !editableServerUrl);
    dom.runtimeModeApply.disabled = !editableServerUrl || !(dom.runtimeModeUrl?.value || "").trim();
  }
  if (dom.runtimeLoginUsername) {
    dom.runtimeLoginUsername.classList.toggle("hidden", !editableServerUrl);
  }
  if (dom.runtimeLoginPassword) {
    dom.runtimeLoginPassword.classList.toggle("hidden", !editableServerUrl);
  }
  if (dom.runtimeLoginApply) {
    dom.runtimeLoginApply.classList.toggle("hidden", !editableServerUrl);
    if (isRuntimeSessionAuthorized()) {
      dom.runtimeLoginApply.textContent = "Logout";
      dom.runtimeLoginApply.disabled = !editableServerUrl;
    } else {
      dom.runtimeLoginApply.textContent = "Login";
      dom.runtimeLoginApply.disabled = !editableServerUrl || !usernameValue || !passwordValue;
    }
  }
  setRuntimeModeBadge();
  setRuntimeAuthIndicators();
  setSourceBadges();
  updateStatusSourceLine();
}

export function setServerFeatureAvailability() {
  const serverAuthorized = isServerAuthorized();

  if (dom.btnRefreshInventory) {
    dom.btnRefreshInventory.disabled = !serverAuthorized;
  }
  if (dom.inventoryPolicyType) {
    dom.inventoryPolicyType.disabled = false;
  }
  if (dom.inventoryNamespace) {
    dom.inventoryNamespace.disabled = false;
  }
  if (dom.inventoryStatus) {
    dom.inventoryStatus.disabled = false;
  }
  if (dom.btnRefreshActivation) {
    dom.btnRefreshActivation.disabled = !serverAuthorized;
  }
  if (dom.activationEnable) {
    dom.activationEnable.disabled = !serverAuthorized;
    if (!serverAuthorized) {
      dom.activationEnable.checked = false;
    }
  }
  if (dom.activationWorldId) {
    dom.activationWorldId.disabled = !serverAuthorized;
  }
  if (dom.activationClientProfile) {
    dom.activationClientProfile.disabled = !serverAuthorized;
  }

  const canSave = serverAuthorized
    && Boolean(state.selectedArtifact?.is_authorable || state.selectedPolicyRecord);
  if (dom.btnSaveFile) {
    dom.btnSaveFile.disabled = !canSave;
  }
}

export function applyRuntimeModeState(runtimeModePayload) {
  state.runtimeMode = runtimeModePayload;
  applyRuntimeModeControls();
  setServerFeatureAvailability();
}

export function applyRuntimeAuthState(runtimeAuthPayload) {
  state.runtimeAuth = runtimeAuthPayload;
  applyRuntimeModeControls();
  setServerFeatureAvailability();
}

export async function getRuntimeModeState() {
  requireRuntimeDeps();
  const payload = await _fetchJson("/api/runtime-mode");
  applyRuntimeModeState(payload);
}

export async function refreshRuntimeAuthState({ silent = false } = {}) {
  requireRuntimeDeps();
  try {
    const payload = await _fetchJson(sessionScopedUrl("/api/runtime-auth"));
    applyRuntimeAuthState(payload);
    if (!silent && payload.status === "authorized") {
      _setStatus("Session authorized (admin/superuser).");
    }
    return payload;
  } catch (error) {
    if (!silent) {
      _setStatus(`Runtime auth check failed: ${error.message}`);
    }
    state.runtimeAuth = {
      status: "error",
      access_granted: false,
      detail: String(error.message || error),
    };
    setRuntimeAuthIndicators();
    setServerFeatureAvailability();
    return null;
  }
}
