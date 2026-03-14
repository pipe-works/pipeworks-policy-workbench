import { dom } from "./dom.js";
import { state } from "./state.js";
import {
  applyRuntimeModeControls,
  isServerAuthorized,
  runtimeAuthStatus,
  runtimeModeLabel,
  sessionScopedUrl,
  setServerFeatureAvailability,
  setSourceBadges,
} from "./runtime.js";

let _fetchJson = null;
let _setStatus = null;
const AUTHORABLE_POLICY_TYPES = new Set([
  "species_block",
  "prompt",
  "image_block",
  "tone_profile",
  "descriptor_layer",
  "registry",
]);

export function configureInventory({ fetchJson, setStatus }) {
  _fetchJson = fetchJson;
  _setStatus = setStatus;
}

function requireInventoryDeps() {
  if (!_fetchJson || !_setStatus) {
    throw new Error("Inventory helpers are not configured.");
  }
}

export function setEditorReadOnlyMode(isReadOnly) {
  dom.fileEditor.readOnly = isReadOnly;
  dom.fileEditor.classList.toggle("is-readonly", isReadOnly);
  if (dom.btnReloadFile) {
    dom.btnReloadFile.disabled = false;
  }
  setServerFeatureAvailability();
}

function renderPolicyTypeOptions(payload) {
  renderSelectOptions({
    selectElement: dom.inventoryPolicyType,
    allLabel: "All types",
    options: Array.isArray(payload?.items) ? payload.items : [],
  });
}

function renderPolicyNamespaceOptions(payload) {
  renderSelectOptions({
    selectElement: dom.inventoryNamespace,
    allLabel: "All namespaces",
    options: Array.isArray(payload?.items) ? payload.items : [],
  });
}

function renderPolicyStatusOptions(payload) {
  renderSelectOptions({
    selectElement: dom.inventoryStatus,
    allLabel: "All statuses",
    options: Array.isArray(payload?.items) ? payload.items : [],
  });
}

function renderPolicyStatusOptionCounts(statusCounts = new Map()) {
  if (!dom.inventoryStatus) {
    return;
  }
  for (const option of Array.from(dom.inventoryStatus.options || [])) {
    const value = String(option.value || "").trim();
    if (!value) {
      continue;
    }
    const count = statusCounts.get(value) || 0;
    option.textContent = `${value} (${count})`;
  }
}

function renderSelectOptions({
  selectElement,
  allLabel,
  options,
}) {
  if (!selectElement) {
    return;
  }

  const previouslySelected = (selectElement.value || "").trim();
  const normalizedOptions = (options || [])
    .map((value) => String(value || "").trim())
    .filter(Boolean);

  selectElement.innerHTML = "";
  const allOption = document.createElement("option");
  allOption.value = "";
  allOption.textContent = allLabel;
  selectElement.appendChild(allOption);

  for (const optionValue of normalizedOptions) {
    const option = document.createElement("option");
    option.value = optionValue;
    option.textContent = optionValue;
    selectElement.appendChild(option);
  }

  if (previouslySelected && normalizedOptions.includes(previouslySelected)) {
    selectElement.value = previouslySelected;
  }
}

async function refreshPolicyTypeOptions({ silent = true } = {}) {
  requireInventoryDeps();
  try {
    const payload = await _fetchJson(sessionScopedUrl("/api/policy-types"));
    renderPolicyTypeOptions(payload);
    if (!silent && payload?.detail) {
      _setStatus(payload.detail);
    }
  } catch (error) {
    renderPolicyTypeOptions({ items: [] });
    if (!silent) {
      _setStatus(`Policy type options load failed: ${error.message}`);
    }
  }
}

export async function refreshPolicyNamespaceOptions({ silent = true } = {}) {
  requireInventoryDeps();
  const selectedPolicyType = (dom.inventoryPolicyType?.value || "").trim();
  const query = new URLSearchParams();
  if (selectedPolicyType) {
    query.set("policy_type", selectedPolicyType);
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  try {
    const payload = await _fetchJson(sessionScopedUrl(`/api/policy-namespaces${suffix}`));
    renderPolicyNamespaceOptions(payload);
    if (!silent && payload?.detail) {
      _setStatus(payload.detail);
    }
  } catch (error) {
    renderPolicyNamespaceOptions({ items: [] });
    if (!silent) {
      _setStatus(`Policy namespace options load failed: ${error.message}`);
    }
  }
}

async function refreshPolicyStatusOptions({ silent = true } = {}) {
  requireInventoryDeps();
  try {
    const payload = await _fetchJson(sessionScopedUrl("/api/policy-statuses"));
    renderPolicyStatusOptions(payload);
    if (!silent && payload?.detail) {
      _setStatus(payload.detail);
    }
  } catch (error) {
    renderPolicyStatusOptions({ items: [] });
    if (!silent) {
      _setStatus(`Policy status options load failed: ${error.message}`);
    }
  }
}

export async function refreshPolicyFilterOptions({ silent = true } = {}) {
  if (!isServerAuthorized()) {
    renderPolicyTypeOptions({ items: [] });
    renderPolicyNamespaceOptions({ items: [] });
    renderPolicyStatusOptions({ items: [] });
    return;
  }
  await refreshPolicyTypeOptions({ silent });
  await refreshPolicyNamespaceOptions({ silent });
  await refreshPolicyStatusOptions({ silent });
}

function buildPolicyInventoryQueryString() {
  const query = new URLSearchParams();
  const policyType = (dom.inventoryPolicyType?.value || "").trim();
  const namespace = (dom.inventoryNamespace?.value || "").trim();
  const status = (dom.inventoryStatus?.value || "").trim();
  if (policyType) {
    query.set("policy_type", policyType);
  }
  if (namespace) {
    query.set("namespace", namespace);
  }
  if (status) {
    query.set("status", status);
  }
  return query.toString();
}

function buildStatusCountsQueryString() {
  const query = new URLSearchParams();
  const policyType = (dom.inventoryPolicyType?.value || "").trim();
  const namespace = (dom.inventoryNamespace?.value || "").trim();
  if (policyType) {
    query.set("policy_type", policyType);
  }
  if (namespace) {
    query.set("namespace", namespace);
  }
  return query.toString();
}

export function buildPolicySelectorLabel(item) {
  return `${item.policy_type}:${item.namespace}:${item.policy_key}:${item.variant}`;
}

function selectedPolicyKey() {
  if (!state.selectedPolicyRecord) {
    return "";
  }
  return `${state.selectedPolicyRecord.policy_id}:${state.selectedPolicyRecord.variant}`;
}

function isAuthorablePolicyType(policyType) {
  return AUTHORABLE_POLICY_TYPES.has(String(policyType || "").trim());
}

function _setCurrentObjectField(field, value) {
  if (!field) {
    return;
  }
  const normalized = String(value || "").trim();
  field.textContent = normalized || "--";
}

function updateCurrentObjectActivationState() {
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

function clearCurrentObjectPanel() {
  _setCurrentObjectField(dom.currentPolicyId, "");
  _setCurrentObjectField(dom.currentPolicyType, "");
  _setCurrentObjectField(dom.currentPolicyNamespace, "");
  _setCurrentObjectField(dom.currentPolicyKey, "");
  _setCurrentObjectField(dom.currentPolicyVariant, "");
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
  _setCurrentObjectField(dom.currentPolicyStatus, policy.status);
  _setCurrentObjectField(dom.currentPolicyVersion, String(policy.policy_version || ""));
  _setCurrentObjectField(dom.currentPolicyContentHash, policy.content_hash);
  _setCurrentObjectField(dom.currentPolicyUpdatedAt, policy.updated_at);
  _setCurrentObjectField(dom.currentPolicyUpdatedBy, policy.updated_by);
  updateCurrentObjectActivationState();
}

function setEditorFromPolicyRecord(policy) {
  const isAuthorable = isAuthorablePolicyType(policy.policy_type);
  state.selectedPolicyRecord = policy;
  state.selectedArtifact = {
    policy_type: policy.policy_type,
    namespace: policy.namespace,
    policy_key: policy.policy_key,
    variant: policy.variant,
    is_authorable: isAuthorable,
  };
  setEditorReadOnlyMode(!isAuthorable);
  dom.editorPath.textContent = `${policy.policy_id}:${policy.variant} · db-object`;
  dom.editorPath.title =
    `${policy.policy_id}:${policy.variant}\nstatus=${policy.status} version=${policy.policy_version}`;
  dom.fileEditor.value = buildRawEditorContentFromPolicy(policy);
  updateCurrentObjectPanel(policy);
  setSourceBadges();
  setServerFeatureAvailability();
}

function buildSpeciesYamlFromText(textValue) {
  const normalized = String(textValue || "").replaceAll("\r\n", "\n").replaceAll("\r", "\n");
  const lines = normalized.split("\n");
  return `text: |\n${lines.map((line) => `  ${line}`).join("\n")}`;
}

function buildRawEditorContentFromPolicy(policy) {
  const content = policy.content || {};
  if (policy.policy_type === "species_block") {
    return buildSpeciesYamlFromText(content.text || "");
  }
  if (policy.policy_type === "prompt") {
    return String(content.text || "");
  }
  if (policy.policy_type === "image_block" || policy.policy_type === "clothing_block") {
    return String(content.text || "");
  }
  return JSON.stringify(content, null, 2);
}

export function renderPolicyInventory(items) {
  state.inventoryItems = items;
  if (dom.inventoryCount) {
    dom.inventoryCount.textContent = `${items.length} policies`;
  }
  if (!dom.inventoryList) {
    return;
  }

  dom.inventoryList.innerHTML = "";
  if (!items.length) {
    const item = document.createElement("li");
    item.className = "report-item report-item--info";
    if (!isServerAuthorized()) {
      item.textContent = "Server mode connected, but admin/superuser session is required.";
    } else {
      item.textContent = "No policies matched current filters.";
    }
    dom.inventoryList.appendChild(item);
    return;
  }

  const selectedKey = selectedPolicyKey();
  for (const itemRow of items) {
    const item = document.createElement("li");
    item.className = "inventory-item";

    const button = document.createElement("button");
    button.type = "button";
    button.className = "inventory-item__button";
    const rowKey = `${itemRow.policy_id}:${itemRow.variant}`;
    if (rowKey === selectedKey) {
      button.classList.add("is-active");
    }
    button.title = buildPolicySelectorLabel(itemRow);
    button.addEventListener("click", () => {
      void loadPolicyObject(itemRow.policy_id, itemRow.variant);
    });

    const top = document.createElement("div");
    top.className = "inventory-item__top";
    const selector = document.createElement("span");
    selector.className = "inventory-item__selector";
    selector.textContent = buildPolicySelectorLabel(itemRow);
    const status = document.createElement("span");
    status.className = "inventory-item__status";
    status.textContent = itemRow.status;
    top.append(selector, status);

    const meta = document.createElement("div");
    meta.className = "inventory-item__meta";
    meta.textContent = `v${itemRow.policy_version} · ${itemRow.updated_at}`;

    button.append(top, meta);
    item.append(button);
    dom.inventoryList.appendChild(item);
  }
}

async function refreshPolicyStatusCounts() {
  requireInventoryDeps();
  if (!isServerAuthorized()) {
    renderPolicyStatusOptionCounts(new Map());
    return;
  }
  try {
    const query = buildStatusCountsQueryString();
    const suffix = query ? `?${query}` : "";
    const payload = await _fetchJson(sessionScopedUrl(`/api/policies${suffix}`));
    const statusCounts = new Map();
    for (const item of payload.items || []) {
      const statusValue = String(item?.status || "").trim();
      if (!statusValue) {
        continue;
      }
      statusCounts.set(statusValue, (statusCounts.get(statusValue) || 0) + 1);
    }
    renderPolicyStatusOptionCounts(statusCounts);
  } catch (_error) {
    renderPolicyStatusOptionCounts(new Map());
  }
}

export async function refreshPolicyInventory() {
  requireInventoryDeps();
  if (!isServerAuthorized()) {
    renderPolicyInventory([]);
    _setStatus("Policy inventory requires an admin/superuser session.");
    return;
  }
  _setStatus("Loading API-first policy inventory...");
  try {
    await refreshPolicyStatusCounts();
    const query = buildPolicyInventoryQueryString();
    const suffix = query ? `?${query}` : "";
    const payload = await _fetchJson(sessionScopedUrl(`/api/policies${suffix}`));
    renderPolicyInventory(payload.items || []);
    _setStatus(`Policy inventory loaded (${payload.item_count || 0} items).`);
  } catch (error) {
    _setStatus(`Policy inventory load failed: ${error.message}`);
  }
}

export async function loadPolicyObject(policyId, variant = "") {
  requireInventoryDeps();
  if (!isServerAuthorized()) {
    _setStatus("Cannot load policy object: admin/superuser session required.");
    return;
  }
  _setStatus(`Loading policy object ${policyId}:${variant || "latest"}...`);
  try {
    const query = new URLSearchParams();
    if ((variant || "").trim()) {
      query.set("variant", variant.trim());
    }
    const suffix = query.toString() ? `?${query.toString()}` : "";
    const payload = await _fetchJson(
      sessionScopedUrl(`/api/policies/${encodeURIComponent(policyId)}${suffix}`)
    );
    setEditorFromPolicyRecord(payload);
    renderPolicyInventory(state.inventoryItems);
    if (state.selectedArtifact?.is_authorable) {
      _setStatus(`Loaded ${payload.policy_id}:${payload.variant} from mud-server API.`);
    } else {
      _setStatus(
        `Loaded ${payload.policy_id}:${payload.variant} from mud-server API (read-only: save not yet supported for ${payload.policy_type}).`
      );
    }
  } catch (error) {
    _setStatus(`Policy object load failed: ${error.message}`);
  }
}

export function readActivationScopeInputs() {
  const worldId = (dom.activationWorldId?.value || "").trim();
  const clientProfile = (dom.activationClientProfile?.value || "").trim();
  return {
    worldId,
    clientProfile,
    scope: clientProfile ? `${worldId}:${clientProfile}` : worldId,
  };
}

export function updateActivationScopeLabel() {
  if (!dom.activationScopeLabel) {
    updateActivationSaveSummary();
    return;
  }
  const { worldId, clientProfile } = readActivationScopeInputs();
  if (!worldId) {
    dom.activationScopeLabel.textContent = "scope: <missing world_id>";
    updateActivationSaveSummary();
    return;
  }
  dom.activationScopeLabel.textContent = clientProfile
    ? `scope: ${worldId}:${clientProfile}`
    : `scope: ${worldId}`;
  updateActivationSaveSummary();
}

export function updateActivationSaveSummary() {
  if (!dom.activationSaveSummary) {
    return;
  }
  const activateAfterSave = Boolean(dom.activationEnable?.checked);
  const { worldId, scope } = readActivationScopeInputs();
  const summaryLabel = dom.activationSaveSummary;
  summaryLabel.classList.remove("activation-save-summary__meta--warning");

  if (!activateAfterSave) {
    summaryLabel.textContent = worldId
      ? `Activation after save: Off · Scope: ${scope}`
      : "Activation after save: Off · Scope: <missing world_id>";
    return;
  }

  if (!worldId) {
    summaryLabel.textContent = "Activation after save: On · Scope: <missing world_id>";
    summaryLabel.classList.add("activation-save-summary__meta--warning");
    return;
  }

  summaryLabel.textContent = `Activation after save: On · Scope: ${scope}`;
}

export function renderActivationMessage(message, tone = "info") {
  if (!dom.activationList) {
    return;
  }
  dom.activationList.innerHTML = "";
  const item = document.createElement("li");
  item.className = `report-item report-item--${tone}`;
  item.textContent = message;
  dom.activationList.appendChild(item);
}

function renderActivationScopePayload(payload) {
  state.latestActivationPayload = payload;
  updateCurrentObjectActivationState();
  if (!dom.activationList) {
    return;
  }

  const items = Array.isArray(payload?.items) ? payload.items : [];
  dom.activationList.innerHTML = "";
  if (!items.length) {
    renderActivationMessage("No active mappings for this scope yet.");
    return;
  }

  const sortedItems = [...items].sort((left, right) => {
    const leftPolicyId = String(left.policy_id || "");
    const rightPolicyId = String(right.policy_id || "");
    return leftPolicyId.localeCompare(rightPolicyId);
  });

  for (const itemRow of sortedItems) {
    const policyId = String(itemRow.policy_id || "<unknown-policy>");
    const variant = String(itemRow.variant || "<unknown-variant>");
    const activatedAt = String(itemRow.activated_at || "").trim();
    const activatedBy = String(itemRow.activated_by || "").trim();
    const suffixParts = [];
    if (activatedAt) {
      suffixParts.push(activatedAt);
    }
    if (activatedBy) {
      suffixParts.push(`by ${activatedBy}`);
    }
    const suffix = suffixParts.length ? ` · ${suffixParts.join(" · ")}` : "";

    const item = document.createElement("li");
    item.className = "report-item report-item--info";
    item.textContent = `${policyId}:${variant}${suffix}`;
    dom.activationList.appendChild(item);
  }
}

export async function refreshActivationScope({ silent = false } = {}) {
  requireInventoryDeps();
  if (!isServerAuthorized()) {
    renderActivationMessage("Activation mapping requires an admin/superuser session.");
    if (!silent) {
      _setStatus("Activation mapping unavailable: admin/superuser session required.");
    }
    return null;
  }

  const { worldId, scope } = readActivationScopeInputs();
  updateActivationScopeLabel();
  if (!worldId) {
    renderActivationMessage("Enter world_id before loading activation mappings.", "warning");
    if (!silent) {
      _setStatus("Activation mapping load skipped: world_id is required.");
    }
    return null;
  }

  if (!silent) {
    _setStatus(`Loading activation mappings for scope ${scope}...`);
  }
  try {
    const query = new URLSearchParams({
      scope,
      effective: "true",
    });
    const payload = await _fetchJson(
      sessionScopedUrl(`/api/policy-activations-live?${query.toString()}`)
    );
    renderActivationScopePayload(payload);
    if (!silent) {
      const itemCount = Array.isArray(payload?.items) ? payload.items.length : 0;
      _setStatus(`Activation mappings loaded for ${scope} (${itemCount} entries).`);
    }
    return payload;
  } catch (error) {
    if (!silent) {
      _setStatus(`Activation mapping load failed: ${error.message}`);
    }
    return null;
  }
}

export function renderUnauthorizedServerState(runtimeAuth = null) {
  state.inventoryItems = [];
  state.selectedPolicyRecord = null;
  state.selectedArtifact = null;
  renderPolicyInventory([]);
  clearCurrentObjectPanel();
  const status = runtimeAuth?.status || runtimeAuthStatus();
  if (status === "forbidden") {
    renderActivationMessage("Server mode connected, but session role is not admin/superuser.");
  } else if (status === "unauthenticated") {
    renderActivationMessage("Server mode connected, but session is invalid or expired.");
  } else {
    renderActivationMessage("Server mode connected, but no session id is configured.");
  }
}
