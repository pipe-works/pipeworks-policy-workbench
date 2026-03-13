import { dom } from "./dom.js";
import { state } from "./state.js";
import { isServerAuthorized } from "./runtime.js";
import {
  buildPolicySelectorLabel,
  loadPolicyObject,
  readActivationScopeInputs,
  refreshActivationScope,
} from "./inventory.js";
import { loadFile } from "./tree.js";
import { markSyncPlanStale } from "./sync_plan.js";

let _fetchJson = null;
let _setStatus = null;

export function configureEditorActions({ fetchJson, setStatus }) {
  _fetchJson = fetchJson;
  _setStatus = setStatus;
}

function requireEditorDeps() {
  if (!_fetchJson || !_setStatus) {
    throw new Error("Editor actions are not configured.");
  }
}

export async function saveCurrentFile() {
  requireEditorDeps();
  if (!isServerAuthorized()) {
    _setStatus("Save unavailable: admin/superuser mud-server session required.");
    return;
  }
  if (!state.selectedArtifact || !state.selectedArtifact.is_authorable) {
    _setStatus("Select an authorable policy object or mapped file before saving.");
    return;
  }

  const activateAfterSave = Boolean(dom.activationEnable?.checked);
  const activationScope = readActivationScopeInputs();
  if (activateAfterSave && !activationScope.worldId) {
    _setStatus("Cannot activate after save: world_id is required.");
    return;
  }

  const targetLabel = state.selectedPath || buildPolicySelectorLabel(state.selectedArtifact);
  _setStatus(
    activateAfterSave
      ? `Saving ${targetLabel} and activating ${activationScope.scope}...`
      : `Saving ${targetLabel} via mud-server policy API...`
  );
  try {
    const savePayload = {
      policy_type: state.selectedArtifact.policy_type,
      namespace: state.selectedArtifact.namespace,
      policy_key: state.selectedArtifact.policy_key,
      variant: state.selectedArtifact.variant,
      raw_content: dom.fileEditor.value,
      schema_version: "1.0",
      status: "draft",
      activate: activateAfterSave,
    };
    if ((state.runtimeSessionId || "").trim()) {
      savePayload.session_id = state.runtimeSessionId.trim();
    }
    if (activateAfterSave) {
      savePayload.world_id = activationScope.worldId;
      if (activationScope.clientProfile) {
        savePayload.client_profile = activationScope.clientProfile;
      }
    }

    const saveResult = await _fetchJson("/api/policy-save", {
      method: "POST",
      body: JSON.stringify(savePayload),
    });

    let statusMessage = `Saved ${saveResult.policy_id}:${saveResult.variant} (v${saveResult.policy_version}).`;
    if (activateAfterSave) {
      const activationPayload = await refreshActivationScope({ silent: true });
      const mappingCount = Array.isArray(activationPayload?.items)
        ? activationPayload.items.length
        : null;
      if (mappingCount === null) {
        statusMessage = `${statusMessage} Activated for scope ${activationScope.scope}.`;
      } else {
        statusMessage = `${statusMessage} Activated for scope ${activationScope.scope} (${mappingCount} mappings).`;
      }
    }
    _setStatus(statusMessage);
    if (state.selectedPolicyRecord) {
      await loadPolicyObject(saveResult.policy_id, saveResult.variant);
    }
    markSyncPlanStale();
  } catch (error) {
    _setStatus(`Save failed: ${error.message}`);
  }
}

export async function reloadCurrentFile() {
  requireEditorDeps();
  if (state.selectedPath) {
    await loadFile(state.selectedPath);
    return;
  }
  if (state.selectedPolicyRecord) {
    await loadPolicyObject(state.selectedPolicyRecord.policy_id, state.selectedPolicyRecord.variant);
    return;
  }
  _setStatus("Select a file or policy object before reloading.");
}
