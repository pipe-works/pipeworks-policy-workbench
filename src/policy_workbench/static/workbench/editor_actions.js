import { dom } from "./dom.js";
import { state } from "./state.js";
import { isServerAuthorized, setServerFeatureAvailability } from "./runtime.js";
import {
  buildPolicySelectorLabel,
  loadPolicyObject,
  readActivationScopeInputs,
  refreshActivationScope,
  setEditorReadOnlyMode,
} from "./inventory.js";
import { setActiveMainTab } from "./tabs.js";

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

function hasUnsavedEditorChanges() {
  return String(dom.fileEditor?.value || "") !== String(state.editorBaseContent || "");
}

function normalizeVariantScopeSegment(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function buildScopedVariantName({ baseVariant, worldId, clientProfile }) {
  const normalizedBaseVariant = String(baseVariant || "").trim() || "v1";
  const worldSegment = normalizeVariantScopeSegment(worldId);
  const clientSegment = normalizeVariantScopeSegment(clientProfile);
  const scopeSuffix = clientSegment
    ? `-w-${worldSegment}-cp-${clientSegment}`
    : `-w-${worldSegment}`;

  if (normalizedBaseVariant.endsWith(scopeSuffix)) {
    return normalizedBaseVariant;
  }

  const stripped = normalizedBaseVariant.replace(/-w-[a-z0-9-]+(?:-cp-[a-z0-9-]+)?$/, "");
  const scopedVariant = `${stripped}${scopeSuffix}`;
  return scopedVariant || normalizedBaseVariant;
}

function saveScopeMode() {
  const mode = String(dom.saveScopeMode?.value || "world_only").trim();
  return mode === "global_update" ? "global_update" : "world_only";
}

async function activatePolicyScope({
  policyId,
  variant,
  worldId,
  clientProfile,
}) {
  const activationPayload = {
    world_id: worldId,
    client_profile: clientProfile || null,
    policy_id: policyId,
    variant,
  };
  if ((state.runtimeSessionId || "").trim()) {
    activationPayload.session_id = state.runtimeSessionId.trim();
  }
  return _fetchJson("/api/policy-activation-set", {
    method: "POST",
    body: JSON.stringify(activationPayload),
  });
}

async function rolloutVariantToOtherWorlds({
  policyId,
  variant,
  selectedWorldId,
  clientProfile,
}) {
  const targetWorldIds = (state.availableWorlds || [])
    .filter((row) => row && row.can_access !== false)
    .map((row) => String(row.id || "").trim())
    .filter((worldId) => worldId && worldId !== selectedWorldId);

  let activatedCount = 0;
  const failedWorldIds = [];
  for (const worldId of targetWorldIds) {
    try {
      await activatePolicyScope({
        policyId,
        variant,
        worldId,
        clientProfile,
      });
      activatedCount += 1;
    } catch (error) {
      failedWorldIds.push(`${worldId} (${error.message})`);
    }
  }

  return {
    activatedCount,
    attemptedCount: targetWorldIds.length,
    failedWorldIds,
  };
}

export function openEditorForCurrentSelection() {
  requireEditorDeps();
  if (!isServerAuthorized()) {
    _setStatus("Edit unavailable: admin/superuser mud-server session required.");
    return;
  }
  if (!state.selectedArtifact || !state.selectedArtifact.is_authorable || !state.selectedPolicyRecord) {
    _setStatus("Select an authorable policy object before entering edit mode.");
    return;
  }
  if (state.editorIsEditing) {
    return;
  }

  state.editorIsEditing = true;
  setEditorReadOnlyMode(false);
  dom.fileEditor?.focus();
  _setStatus(`Edit mode enabled for ${buildPolicySelectorLabel(state.selectedArtifact)}.`);
}

export function closeEditorForCurrentSelection() {
  requireEditorDeps();
  if (!state.selectedArtifact || !state.selectedArtifact.is_authorable || !state.selectedPolicyRecord) {
    return;
  }
  if (!state.editorIsEditing) {
    return;
  }

  if (hasUnsavedEditorChanges()) {
    const shouldDiscard = window.confirm("Discard unsaved changes and close editor?");
    if (!shouldDiscard) {
      return;
    }
  }

  dom.fileEditor.value = String(state.editorBaseContent || "");
  state.editorIsEditing = false;
  setEditorReadOnlyMode(true);
  _setStatus(`Editor closed for ${buildPolicySelectorLabel(state.selectedArtifact)}.`);
}

export function handleEditorInputChange() {
  if (!state.selectedPolicyRecord) {
    return;
  }
  setServerFeatureAvailability();
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
  if (!state.editorIsEditing) {
    _setStatus("Editor is read-only. Click Edit Policy before saving.");
    return;
  }
  if (!hasUnsavedEditorChanges()) {
    _setStatus("No unsaved changes to save.");
    return;
  }

  const scopeMode = saveScopeMode();
  const isWorldOnlyMode = scopeMode === "world_only";
  const rolloutAllWorlds = Boolean(dom.saveRolloutAllWorlds?.checked && isWorldOnlyMode);
  const activateAfterSave = isWorldOnlyMode ? true : Boolean(dom.activationEnable?.checked);
  const activationScope = readActivationScopeInputs();
  if ((activateAfterSave || rolloutAllWorlds) && !activationScope.worldId) {
    _setStatus("Cannot activate after save: select a world first.");
    setActiveMainTab("activation");
    return;
  }

  const targetLabel = buildPolicySelectorLabel(state.selectedArtifact);
  _setStatus(
    isWorldOnlyMode
      ? `Saving ${targetLabel} for selected world scope ${activationScope.scope}...`
      : activateAfterSave
        ? `Saving ${targetLabel} and activating ${activationScope.scope}...`
        : `Saving ${targetLabel} via mud-server policy API...`
  );
  try {
    const resolvedVariant = isWorldOnlyMode
      ? buildScopedVariantName({
          baseVariant: state.selectedArtifact.variant,
          worldId: activationScope.worldId,
          clientProfile: activationScope.clientProfile,
        })
      : state.selectedArtifact.variant;

    const savePayload = {
      policy_type: state.selectedArtifact.policy_type,
      namespace: state.selectedArtifact.namespace,
      policy_key: state.selectedArtifact.policy_key,
      variant: resolvedVariant,
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

    if (isWorldOnlyMode && rolloutAllWorlds) {
      const rolloutResult = await rolloutVariantToOtherWorlds({
        policyId: saveResult.policy_id,
        variant: saveResult.variant,
        selectedWorldId: activationScope.worldId,
        clientProfile: activationScope.clientProfile,
      });
      statusMessage = `${statusMessage} Activated selected scope ${activationScope.scope}; rollout to ${rolloutResult.activatedCount}/${rolloutResult.attemptedCount} other worlds.`;
      if (rolloutResult.failedWorldIds.length) {
        statusMessage = `${statusMessage} Failed: ${rolloutResult.failedWorldIds.join("; ")}`;
      }
      await refreshActivationScope({ silent: true });
      setActiveMainTab("activation");
    } else if (activateAfterSave) {
      const activationPayload = await refreshActivationScope({ silent: true });
      const mappingCount = Array.isArray(activationPayload?.items)
        ? activationPayload.items.length
        : null;
      if (mappingCount === null) {
        statusMessage = `${statusMessage} Activated for scope ${activationScope.scope}.`;
      } else {
        statusMessage = `${statusMessage} Activated for scope ${activationScope.scope} (${mappingCount} mappings).`;
      }
      setActiveMainTab("activation");
    }
    _setStatus(statusMessage);
    if (state.selectedPolicyRecord) {
      await loadPolicyObject(saveResult.policy_id, saveResult.variant);
    }
  } catch (error) {
    _setStatus(`Save failed: ${error.message}`);
  }
}

export async function reloadCurrentFile() {
  requireEditorDeps();
  if (state.editorIsEditing && hasUnsavedEditorChanges()) {
    const shouldReload = window.confirm("Discard unsaved changes and reload latest policy content?");
    if (!shouldReload) {
      return;
    }
  }
  if (state.selectedPolicyRecord) {
    await loadPolicyObject(state.selectedPolicyRecord.policy_id, state.selectedPolicyRecord.variant);
    return;
  }
  _setStatus("Select a policy object before reloading.");
}
