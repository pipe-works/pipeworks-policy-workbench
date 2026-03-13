import { SYNC_STEP_KEYS } from "./constants.js";
import { dom } from "./dom.js";
import { state } from "./state.js";
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
import { loadTree, setTreeCollapsed } from "./tree.js";
import { handleCopyCanonicalHash, initializeHashUi, refreshHashStatus } from "./hash.js";
import { runValidation } from "./validation.js";
import { closeSyncDiffModal } from "./sync_compare.js";
import { applySyncPlan, buildSyncPlan, initializeSyncPlanUi } from "./sync_plan.js";
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

function setActiveSyncStep(stepKey) {
  const normalized = SYNC_STEP_KEYS.has(stepKey) ? stepKey : "build";
  state.activeSyncStep = normalized;

  for (const tab of dom.syncTabs) {
    const isActive = tab.dataset.syncTab === normalized;
    tab.classList.toggle("is-active", isActive);
    tab.setAttribute("aria-selected", isActive ? "true" : "false");
    tab.tabIndex = isActive ? 0 : -1;
  }

  for (const panel of dom.syncPanels) {
    panel.hidden = panel.dataset.syncStep !== normalized;
  }
}

function wireSyncTabs() {
  for (const tab of dom.syncTabs) {
    tab.addEventListener("click", () => {
      const tabKey = tab.dataset.syncTab || "build";
      setActiveSyncStep(tabKey);
    });
  }
}

function wireModalEvents() {
  if (dom.syncDiffBackdrop) {
    dom.syncDiffBackdrop.addEventListener("click", closeSyncDiffModal);
  }
  if (dom.syncDiffClose) {
    dom.syncDiffClose.addEventListener("click", closeSyncDiffModal);
  }
  if (dom.syncDiffCloseX) {
    dom.syncDiffCloseX.addEventListener("click", closeSyncDiffModal);
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeSyncDiffModal();
    }
  });
  if (dom.syncCompareCopyPath) {
    dom.syncCompareCopyPath.addEventListener("click", async () => {
      if (!state.currentComparePath) {
        return;
      }
      try {
        await navigator.clipboard.writeText(state.currentComparePath);
        _setStatus("Compare path copied.");
      } catch {
        _setStatus("Unable to copy compare path.");
      }
    });
  }
}

function wireTreeEvents() {
  if (dom.btnToggleTree) {
    dom.btnToggleTree.addEventListener("click", () => {
      setTreeCollapsed(!state.treeCollapsed);
    });
  }
  if (dom.btnExpandTree) {
    dom.btnExpandTree.addEventListener("click", () => {
      setTreeCollapsed(false);
    });
  }
  dom.btnRefreshTree.addEventListener("click", loadTree);
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
  if (dom.btnRefreshHash) {
    dom.btnRefreshHash.addEventListener("click", refreshHashStatus);
  }
  if (dom.btnCopyHash) {
    dom.btnCopyHash.addEventListener("click", handleCopyCanonicalHash);
  }
  dom.btnSaveFile.addEventListener("click", saveCurrentFile);
  dom.btnReloadFile.addEventListener("click", reloadCurrentFile);
  dom.btnRunValidation.addEventListener("click", runValidation);
  dom.btnBuildSync.addEventListener("click", buildSyncPlan);
  dom.btnApplySync.addEventListener("click", applySyncPlan);
}

async function bootstrapInitialData() {
  setTreeCollapsed(true);
  try {
    await getRuntimeModeState();
    await refreshRuntimeAuthState({ silent: true });
    await refreshPolicyFilterOptions({ silent: true });
  } catch (error) {
    _setStatus(`Runtime mode load failed: ${error.message}`);
  }
  updateActivationScopeLabel();
  renderActivationMessage("Select a scope and click Refresh Scope Mapping.");
  initializeHashUi();
  initializeSyncPlanUi();

  await refreshHashStatus();
  await loadTree();
  if (isServerAuthorized()) {
    await refreshPolicyInventory();
    await refreshActivationScope({ silent: true });
  } else {
    renderUnauthorizedServerState({ status: runtimeAuthStatus() });
  }
  await runValidation();
  await buildSyncPlan();
}

export async function initializeWorkbench() {
  requireBootDeps();
  wireSyncTabs();
  setActiveSyncStep("build");
  wireModalEvents();
  wireTreeEvents();
  wireRuntimeEvents();
  wireInventoryEvents();
  wireActivationEvents();
  wireActionEvents();
  await bootstrapInitialData();
}
