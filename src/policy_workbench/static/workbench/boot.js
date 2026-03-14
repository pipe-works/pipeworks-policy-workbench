import { dom } from "./dom.js";
import {
  applyRuntimeModeControls,
  getRuntimeModeState,
  isServerAuthorized,
  refreshRuntimeAuthState,
  runtimeAuthStatus,
  runtimeModeLabel,
} from "./runtime.js";
import {
  refreshActivationScope,
  refreshPolicyFilterOptions,
  refreshPolicyInventory,
  refreshPolicyNamespaceOptions,
  renderActivationMessage,
  renderUnauthorizedServerState,
  updateActivationScopeLabel,
} from "./inventory.js";
import { reloadCurrentFile, saveCurrentFile } from "./editor_actions.js";
import {
  handleRuntimeLoginButtonAction,
  loginRuntimeSession,
  setRuntimeMode,
} from "./runtime_session.js";

let _setStatus = null;

export function configureBoot({ setStatus }) {
  _setStatus = setStatus;
}

function requireBootDeps() {
  if (!_setStatus) {
    throw new Error("Boot helpers are not configured.");
  }
}

function wireRuntimeEvents() {
  if (dom.runtimeModeSelect) {
    dom.runtimeModeSelect.addEventListener("change", async () => {
      const nextMode = dom.runtimeModeSelect.value;
      try {
        await setRuntimeMode(nextMode);
        _setStatus(`Runtime mode switched to ${runtimeModeLabel()}.`);
      } catch (error) {
        _setStatus(`Runtime mode switch failed: ${error.message}`);
      }
    });
  }
  if (dom.runtimeModeUrl) {
    dom.runtimeModeUrl.addEventListener("input", () => {
      if (dom.runtimeModeApply) {
        dom.runtimeModeApply.disabled = !dom.runtimeModeUrl.value.trim();
      }
    });
    dom.runtimeModeUrl.addEventListener("keydown", async (event) => {
      if (event.key !== "Enter") {
        return;
      }
      event.preventDefault();
      if (!dom.runtimeModeSelect) {
        return;
      }
      try {
        await setRuntimeMode(dom.runtimeModeSelect.value, {
          explicitServerUrl: dom.runtimeModeUrl.value,
        });
        _setStatus(`Runtime mode URL updated for ${runtimeModeLabel()}.`);
      } catch (error) {
        _setStatus(`Runtime mode URL update failed: ${error.message}`);
      }
    });
  }
  if (dom.runtimeLoginUsername) {
    dom.runtimeLoginUsername.addEventListener("input", applyRuntimeModeControls);
    dom.runtimeLoginUsername.addEventListener("keydown", async (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        await loginRuntimeSession();
      }
    });
  }
  if (dom.runtimeLoginPassword) {
    dom.runtimeLoginPassword.addEventListener("input", applyRuntimeModeControls);
    dom.runtimeLoginPassword.addEventListener("keydown", async (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        await loginRuntimeSession();
      }
    });
  }
  if (dom.runtimeLoginApply) {
    dom.runtimeLoginApply.addEventListener("click", async () => {
      await handleRuntimeLoginButtonAction();
    });
  }
  if (dom.runtimeModeApply) {
    dom.runtimeModeApply.addEventListener("click", async () => {
      if (!dom.runtimeModeSelect || !dom.runtimeModeUrl) {
        return;
      }
      try {
        await setRuntimeMode(dom.runtimeModeSelect.value, {
          explicitServerUrl: dom.runtimeModeUrl.value,
        });
        _setStatus(`Runtime mode URL updated for ${runtimeModeLabel()}.`);
      } catch (error) {
        _setStatus(`Runtime mode URL update failed: ${error.message}`);
      }
    });
  }
}

function wireInventoryEvents() {
  if (dom.btnRefreshInventory) {
    dom.btnRefreshInventory.addEventListener("click", refreshPolicyInventory);
  }
  if (dom.inventoryPolicyType) {
    dom.inventoryPolicyType.addEventListener("change", async () => {
      await refreshPolicyNamespaceOptions({ silent: true });
      if (!isServerAuthorized()) {
        return;
      }
      await refreshPolicyInventory();
    });
  }
  if (dom.inventoryNamespace) {
    dom.inventoryNamespace.addEventListener("change", () => {
      if (!isServerAuthorized()) {
        return;
      }
      void refreshPolicyInventory();
    });
  }
  if (dom.inventoryStatus) {
    dom.inventoryStatus.addEventListener("change", () => {
      if (!isServerAuthorized()) {
        return;
      }
      void refreshPolicyInventory();
    });
  }
}

function wireActivationEvents() {
  if (dom.btnRefreshActivation) {
    dom.btnRefreshActivation.addEventListener("click", () => {
      void refreshActivationScope();
    });
  }
  if (dom.activationWorldId) {
    dom.activationWorldId.addEventListener("input", updateActivationScopeLabel);
  }
  if (dom.activationClientProfile) {
    dom.activationClientProfile.addEventListener("input", updateActivationScopeLabel);
  }
}

function wireActionEvents() {
  dom.btnSaveFile.addEventListener("click", saveCurrentFile);
  dom.btnReloadFile.addEventListener("click", reloadCurrentFile);
}

async function bootstrapInitialData() {
  try {
    await getRuntimeModeState();
    await refreshRuntimeAuthState({ silent: true });
    await refreshPolicyFilterOptions({ silent: true });
  } catch (error) {
    _setStatus(`Runtime mode load failed: ${error.message}`);
  }
  updateActivationScopeLabel();
  renderActivationMessage("Select a scope and click Refresh Scope Mapping.");

  if (isServerAuthorized()) {
    await refreshPolicyInventory();
    await refreshActivationScope({ silent: true });
  } else {
    renderUnauthorizedServerState({ status: runtimeAuthStatus() });
  }
}

export async function initializeWorkbench() {
  requireBootDeps();
  wireRuntimeEvents();
  wireInventoryEvents();
  wireActivationEvents();
  wireActionEvents();
  await bootstrapInitialData();
}
