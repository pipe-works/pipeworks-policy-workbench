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
  applyActivationFilters,
  applySelectedActivationStatus,
  refreshActivationScope,
  refreshPolicyFilterOptions,
  refreshPolicyInventory,
  refreshPolicyNamespaceOptions,
  renderActivationMessage,
  renderUnauthorizedServerState,
  setAvailableWorldOptions,
  updateActivationStatusActionState,
  updateActivationSaveSummary,
  updateActivationScopeLabel,
} from "./inventory.js";
import {
  closeEditorForCurrentSelection,
  handleEditorInputChange,
  openEditorForCurrentSelection,
  reloadCurrentFile,
  saveCurrentFile,
} from "./editor_actions.js";
import {
  handleRuntimeLoginButtonAction,
  loginRuntimeSession,
  setRuntimeMode,
} from "./runtime_session.js";
import { setActiveMainTab, wireMainTabEvents } from "./tabs.js";

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

function setWorkspacePanelCollapsed(isCollapsed) {
  if (!dom.workbenchGrid || !dom.workspacePanel || !dom.btnToggleWorkspacePanel) {
    return;
  }

  dom.workbenchGrid.classList.toggle("workbench-grid--right-collapsed", isCollapsed);
  dom.workspacePanel.classList.toggle("is-collapsed", isCollapsed);
  if (dom.workspacePanelContent) {
    dom.workspacePanelContent.hidden = isCollapsed;
  }
  dom.btnToggleWorkspacePanel.setAttribute("aria-expanded", String(!isCollapsed));
  dom.btnToggleWorkspacePanel.setAttribute(
    "aria-label",
    isCollapsed ? "Expand workspace panel" : "Collapse workspace panel"
  );
  dom.btnToggleWorkspacePanel.textContent = isCollapsed ? ">" : "<";
}

function wireWorkspacePanelEvents() {
  if (!dom.btnToggleWorkspacePanel || !dom.workspacePanel) {
    return;
  }
  setWorkspacePanelCollapsed(true);
  dom.btnToggleWorkspacePanel.addEventListener("click", () => {
    const isCurrentlyCollapsed = dom.workspacePanel.classList.contains("is-collapsed");
    setWorkspacePanelCollapsed(!isCurrentlyCollapsed);
  });
}

function wireInventoryEvents() {
  if (dom.inventoryWorld) {
    dom.inventoryWorld.addEventListener("change", () => {
      updateActivationScopeLabel();
      if (!isServerAuthorized()) {
        return;
      }
      void refreshActivationScope({ silent: true });
    });
  }
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
  if (dom.activationClientProfile) {
    dom.activationClientProfile.addEventListener("input", updateActivationScopeLabel);
  }
  if (dom.activationEnable) {
    dom.activationEnable.addEventListener("change", updateActivationSaveSummary);
  }
  if (dom.saveScopeMode) {
    dom.saveScopeMode.addEventListener("change", updateActivationSaveSummary);
  }
  if (dom.saveRolloutAllWorlds) {
    dom.saveRolloutAllWorlds.addEventListener("change", updateActivationSaveSummary);
  }
  if (dom.activationFilterPolicyType) {
    dom.activationFilterPolicyType.addEventListener("change", applyActivationFilters);
  }
  if (dom.activationFilterNamespace) {
    dom.activationFilterNamespace.addEventListener("change", applyActivationFilters);
  }
  if (dom.activationFilterStatus) {
    dom.activationFilterStatus.addEventListener("change", applyActivationFilters);
  }
  if (dom.activationFilterSearch) {
    dom.activationFilterSearch.addEventListener("input", applyActivationFilters);
  }
  if (dom.activationSetStatus) {
    dom.activationSetStatus.addEventListener("change", updateActivationStatusActionState);
  }
  if (dom.btnActivationApplyStatus) {
    dom.btnActivationApplyStatus.addEventListener("click", () => {
      void applySelectedActivationStatus();
    });
  }
}

function wireActionEvents() {
  if (dom.btnEditFile) {
    dom.btnEditFile.addEventListener("click", openEditorForCurrentSelection);
  }
  if (dom.btnCloseFile) {
    dom.btnCloseFile.addEventListener("click", closeEditorForCurrentSelection);
  }
  dom.btnSaveFile.addEventListener("click", saveCurrentFile);
  dom.btnReloadFile.addEventListener("click", reloadCurrentFile);
  if (dom.fileEditor) {
    dom.fileEditor.addEventListener("input", handleEditorInputChange);
  }
  if (dom.btnOpenActivationTab) {
    dom.btnOpenActivationTab.addEventListener("click", () => {
      setActiveMainTab("activation");
    });
  }
}

async function bootstrapInitialData() {
  try {
    await getRuntimeModeState();
    const runtimeAuthPayload = await refreshRuntimeAuthState({ silent: true });
    setAvailableWorldOptions(runtimeAuthPayload?.available_worlds || []);
    await refreshPolicyFilterOptions({ silent: true });
  } catch (error) {
    _setStatus(`Runtime mode load failed: ${error.message}`);
  }
  updateActivationScopeLabel();
  renderActivationMessage("Select a world scope and click Refresh Scope Mapping.");

  if (isServerAuthorized()) {
    await refreshPolicyInventory();
    await refreshActivationScope({ silent: true });
  } else {
    renderUnauthorizedServerState({ status: runtimeAuthStatus() });
  }
}

export async function initializeWorkbench() {
  requireBootDeps();
  wireWorkspacePanelEvents();
  wireMainTabEvents();
  setActiveMainTab("editor");
  wireRuntimeEvents();
  wireInventoryEvents();
  wireActivationEvents();
  wireActionEvents();
  await bootstrapInitialData();
}
