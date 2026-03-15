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
  clearAvailableWorldOptions,
  refreshActivationScope,
  refreshPolicyFilterOptions,
  refreshPolicyInventory,
  setAvailableWorldOptions,
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

export async function setRuntimeMode(modeKey, { explicitServerUrl = null } = {}) {
  requireRuntimeSessionDeps();
  const requestPayload = { mode_key: modeKey };

  // Only treat URL as an override when the user explicitly applies it.
  // Mode-switch events should keep each mode's own active/default URL.
  if (explicitServerUrl !== null) {
    const serverUrl = String(explicitServerUrl || "").trim();
    if (serverUrl) {
      requestPayload.server_url = serverUrl;
    }
  }

  const payload = await _fetchJson("/api/runtime-mode", {
    method: "POST",
    body: JSON.stringify(requestPayload),
  });
  applyRuntimeModeState(payload);
  setRuntimeSessionId("");
  clearAvailableWorldOptions();
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
    if (!payload.success) {
      _setStatus(payload.detail || "Runtime login failed.");
      return;
    }

    setAvailableWorldOptions(payload.available_worlds || []);
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
  try {
    await _fetchJson("/api/runtime-logout", { method: "POST" });
    setRuntimeSessionId("");
    clearAvailableWorldOptions();
    if (dom.runtimeLoginPassword) {
      dom.runtimeLoginPassword.value = "";
    }
    await refreshRuntimeAuthState({ silent: true });
    await refreshPolicyFilterOptions({ silent: true });
    applyRuntimeModeControls();
    setServerFeatureAvailability();

    state.inventoryItems = [];
    renderPolicyInventory([]);
    renderActivationMessage("Server mode connected, but no active runtime session is configured.");
    _setStatus(`Logged out from ${runtimeModeLabel()}.`);
  } catch (error) {
    _setStatus(`Runtime logout failed: ${error.message}`);
  }
}

export async function handleRuntimeLoginButtonAction() {
  requireRuntimeSessionDeps();
  if (isRuntimeSessionAuthorized()) {
    await logoutRuntimeSession();
    return;
  }
  await loginRuntimeSession();
}
