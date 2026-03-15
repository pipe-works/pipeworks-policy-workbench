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

function updateEditorLineNumberGutter() {
  if (!dom.editorLineNumbers || !dom.fileEditor) {
    return;
  }
  const editorStyles = window.getComputedStyle(dom.fileEditor);
  dom.editorLineNumbers.style.fontFamily = editorStyles.fontFamily;
  dom.editorLineNumbers.style.fontSize = editorStyles.fontSize;
  dom.editorLineNumbers.style.fontWeight = editorStyles.fontWeight;
  dom.editorLineNumbers.style.lineHeight = editorStyles.lineHeight;
  dom.editorLineNumbers.style.paddingTop = editorStyles.paddingTop;
  dom.editorLineNumbers.style.paddingBottom = editorStyles.paddingBottom;

  const lineCount = Math.max(1, String(dom.fileEditor.value || "").split("\n").length);
  const digitCount = Math.max(2, String(lineCount).length);
  dom.editorLineNumbers.style.width = `${digitCount + 2}ch`;

  const lines = [];
  for (let index = 1; index <= lineCount; index += 1) {
    lines.push(String(index));
  }
  dom.editorLineNumbers.textContent = lines.join("\n");
  dom.editorLineNumbers.scrollTop = dom.fileEditor.scrollTop;
}

export function refreshEditorLineNumbers() {
  updateEditorLineNumberGutter();
}

const STRUCTURED_POLICY_TYPES = new Set([
  "species_block",
  "clothing_block",
  "tone_profile",
  "descriptor_layer",
  "registry",
]);

const TEXT_OR_OBJECT_POLICY_TYPES = new Set(["prompt", "image_block"]);

function setEditorLintStatus({ tone, message }) {
  if (!dom.editorLintStatus) {
    return;
  }
  dom.editorLintStatus.classList.remove(
    "editor-lint-status--muted",
    "editor-lint-status--ok",
    "editor-lint-status--warn",
    "editor-lint-status--err"
  );
  dom.editorLintStatus.classList.add(`editor-lint-status--${tone}`);
  dom.editorLintStatus.textContent = message;
}

function setEditorValidationDetails({ tone, message }) {
  if (!dom.editorValidationDetails) {
    return;
  }
  dom.editorValidationDetails.classList.remove(
    "editor-validation-details--muted",
    "editor-validation-details--ok",
    "editor-validation-details--warn",
    "editor-validation-details--err"
  );
  dom.editorValidationDetails.classList.add(`editor-validation-details--${tone}`);
  dom.editorValidationDetails.textContent = message;
}

function clearEditorValidationDetails() {
  setEditorValidationDetails({
    tone: "muted",
    message: "Run Validate Policy to see server-side validation details.",
  });
}

function splitValidationDetails(rawDetail) {
  const detail = String(rawDetail || "").trim();
  if (!detail) {
    return [];
  }
  const lines = detail
    .split(/;\s+|\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (!lines.length) {
    return [];
  }
  return lines;
}

function formatValidationFailureMessage(rawDetail) {
  const details = splitValidationDetails(rawDetail);
  if (!details.length) {
    return "Validation failed, but no detailed error payload was returned.";
  }
  if (details.length === 1) {
    return `Validation issue:\n- ${details[0]}`;
  }
  return `Validation issues (${details.length}):\n- ${details.join("\n- ")}`;
}

function normalizeJsonSyntaxError(error) {
  const message = String(error?.message || "").trim();
  if (!message) {
    return "Invalid JSON syntax.";
  }
  const lineColumnMatch = message.match(/\(line\s+(\d+)\s+column\s+(\d+)\)$/i);
  const withoutPosition = message
    .replace(/\s+at position\s+\d+(?:\s+\(line\s+\d+\s+column\s+\d+\))?$/i, "")
    .trim();
  if (lineColumnMatch) {
    const line = lineColumnMatch[1];
    const column = lineColumnMatch[2];
    return `Invalid JSON syntax at line ${line}, column ${column}: ${withoutPosition || message}`;
  }
  return `Invalid JSON syntax: ${withoutPosition || message}`;
}

function parseJsonObject(rawContent) {
  let parsed;
  try {
    parsed = JSON.parse(rawContent);
  } catch (error) {
    return {
      ok: false,
      message: normalizeJsonSyntaxError(error),
    };
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return {
      ok: false,
      message: "Expected a JSON object at the top level.",
    };
  }
  return {
    ok: true,
    message: "Valid JSON object syntax.",
  };
}

function evaluateEditorLintState() {
  if (!state.selectedPolicyRecord || !state.selectedArtifact) {
    return {
      tone: "muted",
      message: "Select a policy object to begin editing.",
    };
  }
  if (!state.editorIsEditing) {
    return {
      tone: "muted",
      message: "Read-only. Click Edit Policy to lint and validate draft changes.",
    };
  }

  const policyType = String(state.selectedArtifact.policy_type || "").trim();
  const rawContent = String(dom.fileEditor?.value || "");
  const trimmed = rawContent.trim();
  if (!trimmed) {
    return {
      tone: "warn",
      message: "Editor is empty. Save/Validate will fail until content is provided.",
    };
  }

  const looksLikeJson = trimmed.startsWith("{") || trimmed.startsWith("[");

  if (STRUCTURED_POLICY_TYPES.has(policyType)) {
    const jsonCheck = parseJsonObject(rawContent);
    if (jsonCheck.ok) {
      return { tone: "ok", message: jsonCheck.message };
    }
    if (!looksLikeJson) {
      return {
        tone: "err",
        message: "Canonical editor content must be valid JSON object text.",
      };
    }
    return { tone: "err", message: jsonCheck.message };
  }

  if (TEXT_OR_OBJECT_POLICY_TYPES.has(policyType)) {
    if (!looksLikeJson) {
      return {
        tone: "ok",
        message: "Text mode syntax is acceptable. Use Validate for canonical checks.",
      };
    }

    const jsonCheck = parseJsonObject(rawContent);
    if (jsonCheck.ok) {
      return {
        tone: "ok",
        message: "Valid JSON object syntax for text/object policy content.",
      };
    }
    return {
      tone: "warn",
      message: `${jsonCheck.message}. Save will treat this as plain text.`,
    };
  }

  return {
    tone: "muted",
    message: "No local lint rules for this policy type. Use Validate for server checks.",
  };
}

export function refreshEditorLintStatus() {
  const lintState = evaluateEditorLintState();
  setEditorLintStatus(lintState);
  updateEditorLineNumberGutter();
  return lintState;
}

export function resetEditorValidationDetails() {
  clearEditorValidationDetails();
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

function resolveSaveMutationInputs() {
  const isWorldOnlyMode = saveScopeMode() === "world_only";
  const rolloutAllWorlds = Boolean(dom.saveRolloutAllWorlds?.checked && isWorldOnlyMode);
  const activateAfterSave = isWorldOnlyMode ? true : Boolean(dom.activationEnable?.checked);
  const activationScope = readActivationScopeInputs();
  const resolvedVariant = isWorldOnlyMode && activationScope.worldId
    ? buildScopedVariantName({
        baseVariant: state.selectedArtifact.variant,
        worldId: activationScope.worldId,
        clientProfile: activationScope.clientProfile,
      })
    : state.selectedArtifact.variant;
  return {
    isWorldOnlyMode,
    rolloutAllWorlds,
    activateAfterSave,
    activationScope,
    resolvedVariant,
  };
}

function buildPolicyMutationPayload({ resolvedVariant, activateAfterSave }) {
  return {
    policy_type: state.selectedArtifact.policy_type,
    namespace: state.selectedArtifact.namespace,
    policy_key: state.selectedArtifact.policy_key,
    variant: resolvedVariant,
    raw_content: String(dom.fileEditor?.value || ""),
    schema_version: String(state.selectedPolicyRecord?.schema_version || "1.0"),
    status: "draft",
    activate: activateAfterSave,
  };
}

function preflightStructuredJsonOrReport({ actionLabel }) {
  const policyType = String(state.selectedArtifact?.policy_type || "").trim();
  if (!STRUCTURED_POLICY_TYPES.has(policyType)) {
    return true;
  }
  const jsonCheck = parseJsonObject(String(dom.fileEditor?.value || ""));
  if (jsonCheck.ok) {
    return true;
  }
  setEditorLintStatus({
    tone: "err",
    message: jsonCheck.message,
  });
  setEditorValidationDetails({
    tone: "err",
    message: `Cannot ${actionLabel}.\n- ${jsonCheck.message}`,
  });
  _setStatus(`${actionLabel} blocked: ${jsonCheck.message}`);
  return false;
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
  refreshEditorLintStatus();
  clearEditorValidationDetails();
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
  refreshEditorLintStatus();
  clearEditorValidationDetails();
  _setStatus(`Editor closed for ${buildPolicySelectorLabel(state.selectedArtifact)}.`);
}

export function handleEditorInputChange() {
  if (!state.selectedPolicyRecord) {
    return;
  }
  refreshEditorLintStatus();
  setEditorValidationDetails({
    tone: "muted",
    message: "Draft changed. Run Validate Policy again to refresh server-side feedback.",
  });
  setServerFeatureAvailability();
}

export async function validateCurrentFile() {
  requireEditorDeps();
  if (!isServerAuthorized()) {
    _setStatus("Validate unavailable: admin/superuser mud-server session required.");
    return;
  }
  if (!state.selectedArtifact || !state.selectedArtifact.is_authorable || !state.selectedPolicyRecord) {
    _setStatus("Select an authorable policy object before validating.");
    return;
  }

  refreshEditorLintStatus();
  if (!preflightStructuredJsonOrReport({ actionLabel: "validate" })) {
    return;
  }
  const { isWorldOnlyMode, activationScope, resolvedVariant } = resolveSaveMutationInputs();
  const targetLabel = buildPolicySelectorLabel(state.selectedArtifact);
  const scopeSuffix = isWorldOnlyMode && activationScope.worldId
    ? ` (world scope ${activationScope.scope})`
    : "";
  _setStatus(`Validating ${targetLabel}${scopeSuffix}...`);

  try {
    const validatePayload = buildPolicyMutationPayload({
      resolvedVariant,
      activateAfterSave: false,
    });
    const validateResult = await _fetchJson("/api/policy-validate", {
      method: "POST",
      body: JSON.stringify(validatePayload),
    });
    setEditorLintStatus({
      tone: "ok",
      message: "Server validation passed for current draft.",
    });
    setEditorValidationDetails({
      tone: "ok",
      message:
        `Validation passed for ${validateResult.policy_id}:${validateResult.variant}. `
        + `run_id=${validateResult.validation_run_id} next_policy_version=${validateResult.policy_version}`,
    });
    _setStatus(
      `Validation passed for ${validateResult.policy_id}:${validateResult.variant} `
      + `(run ${validateResult.validation_run_id}, next v${validateResult.policy_version}).`
    );
  } catch (error) {
    const errorDetail = String(error?.message || "").trim();
    const firstIssue = splitValidationDetails(errorDetail)[0] || errorDetail || "Validation failed.";
    setEditorLintStatus({
      tone: "err",
      message: firstIssue,
    });
    setEditorValidationDetails({
      tone: "err",
      message: formatValidationFailureMessage(errorDetail),
    });
    _setStatus(`Validation failed: ${firstIssue}`);
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
  if (!state.editorIsEditing) {
    _setStatus("Editor is read-only. Click Edit Policy before saving.");
    return;
  }
  if (!hasUnsavedEditorChanges()) {
    _setStatus("No unsaved changes to save.");
    return;
  }
  refreshEditorLintStatus();
  if (!preflightStructuredJsonOrReport({ actionLabel: "save" })) {
    return;
  }

  const {
    isWorldOnlyMode,
    rolloutAllWorlds,
    activateAfterSave,
    activationScope,
    resolvedVariant,
  } = resolveSaveMutationInputs();
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
    const savePayload = buildPolicyMutationPayload({ resolvedVariant, activateAfterSave });
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
  refreshEditorLintStatus();
  clearEditorValidationDetails();
  _setStatus("Select a policy object before reloading.");
}
