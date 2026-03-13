import { dom } from "./dom.js";
import { state } from "./state.js";
import {
  applyRuntimeModeControls,
  applyRuntimeModeState,
  isRuntimeSessionAuthorized,
  isServerAuthorized,
  refreshRuntimeAuthState,
  runtimeModeLabel,
  setRuntimeSessionId,
  setServerFeatureAvailability,
} from "./runtime.js";
import {
  refreshActivationScope,
  refreshPolicyFilterOptions,
  refreshPolicyInventory,
  renderActivationMessage,
  renderPolicyInventory,
  renderUnauthorizedServerState,
} from "./inventory.js";

let _fetchJson = null;
let _setStatus = null;

export function configureRuntimeSession({ fetchJson, setStatus }) {
  _fetchJson = fetchJson;
  _setStatus = setStatus;
}

function requireRuntimeSessionDeps() {
  if (!_fetchJson || !_setStatus) {
    throw new Error("Runtime session helpers are not configured.");
  }
}

function selectedRuntimeModeServerUrl(modeKey) {
  const option = state.runtimeModeOptionsByKey.get(modeKey) || null;
  if (!option || option.source_kind !== "server_api") {
    return "";
  }

  const typedUrl = (dom.runtimeModeUrl?.value || "").trim();
  if (typedUrl) {
    return typedUrl;
  }
  const activeServerUrl = (option.active_server_url || "").trim();
  if (activeServerUrl) {
    return activeServerUrl;
  }
  return (option.default_server_url || "").trim();
}

export async function setRuntimeMode(modeKey, { explicitServerUrl = null } = {}) {
  requireRuntimeSessionDeps();
  const requestPayload = { mode_key: modeKey };
  const serverUrl = explicitServerUrl !== null
    ? String(explicitServerUrl || "").trim()
    : selectedRuntimeModeServerUrl(modeKey);
  if (serverUrl) {
    requestPayload.server_url = serverUrl;
  }

  const payload = await _fetchJson("/api/runtime-mode", {
    method: "POST",
    body: JSON.stringify(requestPayload),
  });
  applyRuntimeModeState(payload);
  setRuntimeSessionId("");
  const runtimeAuth = await refreshRuntimeAuthState({ silent: true });
  await refreshPolicyFilterOptions({ silent: true });

  if (isServerAuthorized()) {
    await refreshPolicyInventory();
    await refreshActivationScope({ silent: true });
  } else {
    renderUnauthorizedServerState(runtimeAuth);
  }
}

export async function loginRuntimeSession() {
  requireRuntimeSessionDeps();
  const username = (dom.runtimeLoginUsername?.value || "").trim();
  const password = (dom.runtimeLoginPassword?.value || "").trim();
  if (!username || !password) {
    _setStatus("Username and password are required for runtime login.");
    return;
  }

  _setStatus(`Logging in to ${runtimeModeLabel()}...`);
  try {
    const payload = await _fetchJson("/api/runtime-login", {
      method: "POST",
      body: JSON.stringify({
        username,
        password,
      }),
    });
    if (!payload.success || !payload.session_id) {
      _setStatus(payload.detail || "Runtime login failed.");
      return;
    }

    setRuntimeSessionId(payload.session_id);
    if (dom.runtimeLoginPassword) {
      dom.runtimeLoginPassword.value = "";
    }
    await refreshRuntimeAuthState({ silent: true });
    await refreshPolicyFilterOptions({ silent: true });
    applyRuntimeModeControls();
    setServerFeatureAvailability();

    if (isServerAuthorized()) {
      await refreshPolicyInventory();
      await refreshActivationScope({ silent: true });
      _setStatus(`Login successful as ${payload.role}.`);
      return;
    }

    _setStatus(payload.detail || "Login succeeded, but role is not authorized.");
  } catch (error) {
    _setStatus(`Runtime login failed: ${error.message}`);
  }
}

async function logoutRuntimeSession() {
  requireRuntimeSessionDeps();
  if (!(state.runtimeSessionId || "").trim()) {
    _setStatus("No active runtime session to log out.");
    return;
  }

  setRuntimeSessionId("");
  if (dom.runtimeLoginPassword) {
    dom.runtimeLoginPassword.value = "";
  }
  await refreshRuntimeAuthState({ silent: true });
  await refreshPolicyFilterOptions({ silent: true });
  applyRuntimeModeControls();
  setServerFeatureAvailability();

  state.inventoryItems = [];
  renderPolicyInventory([]);
  renderActivationMessage("Server mode connected, but no session id is configured.");
  _setStatus(`Logged out from ${runtimeModeLabel()}.`);
}

export async function handleRuntimeLoginButtonAction() {
  requireRuntimeSessionDeps();
  if (isRuntimeSessionAuthorized()) {
    await logoutRuntimeSession();
    return;
  }
  await loginRuntimeSession();
}
