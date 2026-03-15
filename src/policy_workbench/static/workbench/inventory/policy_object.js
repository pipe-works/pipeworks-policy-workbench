import { dom } from "../dom.js";
import { state } from "../state.js";
import { setServerFeatureAvailability, setSourceBadges } from "../runtime.js";
import { buildPolicySelectorLabel, isAuthorablePolicyType } from "./policy_selector.js";

export function setEditorReadOnlyMode(isReadOnly) {
  dom.fileEditor.readOnly = isReadOnly;
  dom.fileEditor.classList.toggle("is-readonly", isReadOnly);
  setServerFeatureAvailability();
}

function _setCurrentObjectField(field, value) {
  if (!field) {
    return;
  }
  const normalized = String(value || "").trim();
  field.textContent = normalized || "--";
}

export function updateCurrentObjectActivationState() {
  if (!dom.currentPolicyActivation) {
    return;
  }
  if (!state.selectedPolicyRecord) {
    dom.currentPolicyActivation.textContent = "Not activated";
    return;
  }
  const selectedPolicyId = String(state.selectedPolicyRecord.policy_id || "").trim();
  const selectedVariant = String(state.selectedPolicyRecord.variant || "").trim();
  const activationItems = Array.isArray(state.latestActivationPayload?.items)
    ? state.latestActivationPayload.items
    : [];
  const activationEntry = activationItems.find(
    (item) => String(item?.policy_id || "").trim() === selectedPolicyId
  );
  if (!activationEntry) {
    dom.currentPolicyActivation.textContent = "Not activated in selected scope";
    return;
  }
  const activatedVariant = String(activationEntry.variant || "").trim();
  if (activatedVariant === selectedVariant) {
    dom.currentPolicyActivation.textContent = `Activated variant: ${activatedVariant}`;
    return;
  }
  dom.currentPolicyActivation.textContent =
    `Activated variant: ${activatedVariant} (selected: ${selectedVariant})`;
}

export function clearCurrentObjectPanel() {
  _setCurrentObjectField(dom.currentPolicyId, "");
  _setCurrentObjectField(dom.currentPolicyType, "");
  _setCurrentObjectField(dom.currentPolicyNamespace, "");
  _setCurrentObjectField(dom.currentPolicyKey, "");
  _setCurrentObjectField(dom.currentPolicyVariant, "");
  _setCurrentObjectField(dom.currentPolicySchemaVersion, "");
  _setCurrentObjectField(dom.currentPolicyStatus, "");
  _setCurrentObjectField(dom.currentPolicyVersion, "");
  _setCurrentObjectField(dom.currentPolicyContentHash, "");
  _setCurrentObjectField(dom.currentPolicyUpdatedAt, "");
  _setCurrentObjectField(dom.currentPolicyUpdatedBy, "");
  updateCurrentObjectActivationState();
}

function updateCurrentObjectPanel(policy) {
  if (!policy) {
    clearCurrentObjectPanel();
    return;
  }
  _setCurrentObjectField(dom.currentPolicyId, policy.policy_id);
  _setCurrentObjectField(dom.currentPolicyType, policy.policy_type);
  _setCurrentObjectField(dom.currentPolicyNamespace, policy.namespace);
  _setCurrentObjectField(dom.currentPolicyKey, policy.policy_key);
  _setCurrentObjectField(dom.currentPolicyVariant, policy.variant);
  _setCurrentObjectField(dom.currentPolicySchemaVersion, policy.schema_version);
  _setCurrentObjectField(dom.currentPolicyStatus, policy.status);
  _setCurrentObjectField(dom.currentPolicyVersion, String(policy.policy_version ?? ""));
  _setCurrentObjectField(dom.currentPolicyContentHash, policy.content_hash);
  _setCurrentObjectField(dom.currentPolicyUpdatedAt, policy.updated_at);
  _setCurrentObjectField(dom.currentPolicyUpdatedBy, policy.updated_by);
  updateCurrentObjectActivationState();
}

function buildRawEditorContentFromPolicy(policy) {
  const content = policy.content || {};
  // Render canonical DB/API payload for every policy type so operators can
  // inspect/edit the exact object shape persisted server-side.
  return JSON.stringify(content, null, 2);
}

export function setEditorFromPolicyRecord(policy) {
  const isAuthorable = isAuthorablePolicyType(policy.policy_type);
  const rawEditorContent = buildRawEditorContentFromPolicy(policy);
  state.selectedPolicyRecord = policy;
  state.selectedArtifact = {
    policy_type: policy.policy_type,
    namespace: policy.namespace,
    policy_key: policy.policy_key,
    variant: policy.variant,
    is_authorable: isAuthorable,
  };
  state.editorIsEditing = false;
  state.editorBaseContent = rawEditorContent;
  setEditorReadOnlyMode(true);
  dom.editorPath.textContent = `${policy.policy_id}:${policy.variant} · db-object`;
  dom.editorPath.title =
    `${policy.policy_id}:${policy.variant}\nstatus=${policy.status} version=${policy.policy_version}`;
  dom.fileEditor.value = rawEditorContent;
  updateCurrentObjectPanel(policy);
  setSourceBadges();
  setServerFeatureAvailability();
}

export { buildPolicySelectorLabel };
