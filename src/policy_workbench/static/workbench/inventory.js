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
  "clothing_block",
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
  const statusItems = (Array.isArray(payload?.items) ? payload.items : [])
    .map((value) => String(value || "").trim())
    .filter(Boolean);
  state.policyStatusOptions = statusItems;
  renderSelectOptions({
    selectElement: dom.inventoryStatus,
    allLabel: "All statuses",
    options: statusItems,
  });
  renderActivationSetStatusOptions();
}

function normalizeWorldRows(worldRows) {
  const normalizedRows = [];
  const seenIds = new Set();
  for (const row of worldRows || []) {
    if (!row || typeof row !== "object") {
      continue;
    }
    const worldId = String(row.id || "").trim();
    if (!worldId || seenIds.has(worldId)) {
      continue;
    }
    seenIds.add(worldId);
    normalizedRows.push({
      ...row,
      id: worldId,
      name: String(row.name || "").trim(),
      can_access: row.can_access !== false,
      is_active: row.is_active !== false,
    });
  }
  return normalizedRows;
}

function choosePreferredWorldId(worldRows, preferredWorldId, previousWorldId) {
  const availableIds = new Set((worldRows || []).map((row) => row.id));
  const preferred = String(preferredWorldId || "").trim();
  if (preferred && availableIds.has(preferred)) {
    return preferred;
  }
  const previous = String(previousWorldId || "").trim();
  if (previous && availableIds.has(previous)) {
    return previous;
  }

  const defaultWorld = (worldRows || []).find((row) => row.is_active && row.can_access);
  if (defaultWorld) {
    return defaultWorld.id;
  }
  return String(worldRows?.[0]?.id || "").trim();
}

function buildWorldLabel(worldRow) {
  const worldId = String(worldRow.id || "").trim();
  const worldName = String(worldRow.name || "").trim();
  const label = worldName || worldId;

  const suffixes = [];
  if (!worldRow.is_active) {
    suffixes.push("inactive");
  }
  if (!worldRow.can_access) {
    suffixes.push("locked");
  }
  if (suffixes.length) {
    return `${label} [${suffixes.join(", ")}]`;
  }
  return label;
}

export function setAvailableWorldOptions(worldRows, { preferredWorldId = "" } = {}) {
  const normalizedRows = normalizeWorldRows(worldRows);
  state.availableWorlds = normalizedRows;
  if (!dom.inventoryWorld) {
    state.selectedWorldId = choosePreferredWorldId(
      normalizedRows,
      preferredWorldId,
      state.selectedWorldId
    );
    return;
  }

  const previouslySelected = String(dom.inventoryWorld.value || "").trim();
  const nextWorldId = choosePreferredWorldId(normalizedRows, preferredWorldId, previouslySelected);
  dom.inventoryWorld.innerHTML = "";

  if (!normalizedRows.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No worlds available";
    dom.inventoryWorld.appendChild(option);
    dom.inventoryWorld.value = "";
    state.selectedWorldId = "";
    updateActivationScopeLabel();
    setServerFeatureAvailability();
    return;
  }

  for (const worldRow of normalizedRows) {
    const option = document.createElement("option");
    option.value = worldRow.id;
    option.textContent = buildWorldLabel(worldRow);
    dom.inventoryWorld.appendChild(option);
  }
  if (nextWorldId) {
    dom.inventoryWorld.value = nextWorldId;
  }

  state.selectedWorldId = String(dom.inventoryWorld.value || "").trim();
  updateActivationScopeLabel();
  setServerFeatureAvailability();
}

export function clearAvailableWorldOptions() {
  setAvailableWorldOptions([], { preferredWorldId: "" });
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

function renderActivationSetStatusOptions() {
  if (!dom.activationSetStatus) {
    return;
  }
  const previousValue = String(dom.activationSetStatus.value || "").trim();
  const statusOptions = (state.policyStatusOptions || [])
    .map((value) => String(value || "").trim())
    .filter(Boolean);

  dom.activationSetStatus.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Select status";
  dom.activationSetStatus.appendChild(placeholder);

  for (const statusValue of statusOptions) {
    const option = document.createElement("option");
    option.value = statusValue;
    option.textContent = statusValue;
    dom.activationSetStatus.appendChild(option);
  }

  if (previousValue && statusOptions.includes(previousValue)) {
    dom.activationSetStatus.value = previousValue;
  }
  updateActivationStatusActionState();
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

function setEditorFromPolicyRecord(policy) {
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

function buildRawEditorContentFromPolicy(policy) {
  const content = policy.content || {};
  // Render canonical DB/API payload for every policy type so operators can
  // inspect/edit the exact object shape persisted server-side.
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
    const item = document.createElement("div");
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
  const table = document.createElement("table");
  table.className = "inventory-table inventory-table--policy";
  table.setAttribute("aria-label", "Policy inventory table");

  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  for (const label of ["Policy", "Status", "Version", "Updated"]) {
    const th = document.createElement("th");
    th.scope = "col";
    th.textContent = label;
    headerRow.appendChild(th);
  }
  thead.appendChild(headerRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");

  const loadPolicyFromInventoryRow = (itemRow) => {
    void loadPolicyObject(itemRow.policy_id, itemRow.variant);
  };

  const createCell = (text, label, className = "") => {
    const cell = document.createElement("td");
    cell.textContent = String(text ?? "").trim() || "--";
    cell.setAttribute("data-label", label);
    if (className) {
      cell.className = className;
    }
    return cell;
  };

  for (const itemRow of items) {
    const row = document.createElement("tr");
    row.className = "inventory-table__row";
    const rowKey = `${itemRow.policy_id}:${itemRow.variant}`;
    if (rowKey === selectedKey) {
      row.classList.add("is-active");
    }
    row.tabIndex = 0;
    row.title = buildPolicySelectorLabel(itemRow);
    row.addEventListener("click", () => loadPolicyFromInventoryRow(itemRow));
    row.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }
      event.preventDefault();
      loadPolicyFromInventoryRow(itemRow);
    });

    row.append(
      createCell(buildPolicySelectorLabel(itemRow), "Policy", "inventory-table__policy"),
      createCell(itemRow.status, "Status", "inventory-table__status"),
      createCell(`v${itemRow.policy_version ?? ""}`, "Version", "inventory-table__version"),
      createCell(itemRow.updated_at, "Updated", "inventory-table__updated"),
    );
    tbody.appendChild(row);
  }

  table.appendChild(tbody);
  dom.inventoryList.appendChild(table);
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
  const worldId = (dom.inventoryWorld?.value || state.selectedWorldId || "").trim();
  const clientProfile = (dom.activationClientProfile?.value || "").trim();
  state.selectedWorldId = worldId;
  return {
    worldId,
    clientProfile,
    scope: clientProfile ? `${worldId}:${clientProfile}` : worldId,
  };
}

function updateActivationWorldDisplay() {
  if (!dom.activationWorldDisplay) {
    return;
  }
  const worldId = String(dom.inventoryWorld?.value || state.selectedWorldId || "").trim();
  dom.activationWorldDisplay.textContent = worldId
    ? `World: ${worldId}`
    : "World: none selected";
}

export function updateActivationScopeLabel() {
  updateActivationWorldDisplay();
  if (!dom.activationScopeLabel) {
    updateActivationSaveSummary();
    return;
  }
  const { worldId, clientProfile } = readActivationScopeInputs();
  if (!worldId) {
    dom.activationScopeLabel.textContent = "Scope: none selected";
    updateActivationSaveSummary();
    return;
  }
  dom.activationScopeLabel.textContent = clientProfile
    ? `Scope: ${worldId}:${clientProfile}`
    : `Scope: ${worldId}`;
  updateActivationSaveSummary();
}

export function updateActivationSaveSummary() {
  if (!dom.activationSaveSummary) {
    return;
  }
  const saveScopeMode = String(dom.saveScopeMode?.value || "world_only").trim();
  const isWorldOnlyMode = saveScopeMode !== "global_update";
  const rolloutAllWorlds = Boolean(dom.saveRolloutAllWorlds?.checked);
  if (dom.activationEnable) {
    if (isWorldOnlyMode) {
      dom.activationEnable.checked = true;
    }
  }
  if (dom.saveRolloutAllWorldsRow) {
    dom.saveRolloutAllWorldsRow.hidden = !isWorldOnlyMode;
  }
  if (dom.activationEnableRow) {
    dom.activationEnableRow.hidden = isWorldOnlyMode;
  }
  const activateAfterSave = isWorldOnlyMode ? true : Boolean(dom.activationEnable?.checked);
  const { worldId, scope } = readActivationScopeInputs();
  const summaryLabel = dom.activationSaveSummary;
  summaryLabel.classList.remove("activation-save-summary__meta--warning");

  if (isWorldOnlyMode) {
    if (!worldId) {
      summaryLabel.textContent = "Will save only for the current world. Choose a world first.";
      summaryLabel.classList.add("activation-save-summary__meta--warning");
      setServerFeatureAvailability();
      return;
    }
    summaryLabel.textContent = rolloutAllWorlds
      ? `Will save for ${scope}, then apply the same variant to all accessible worlds.`
      : `Will save for ${scope} only. Other worlds stay unchanged.`;
    setServerFeatureAvailability();
    return;
  }

  if (!activateAfterSave) {
    summaryLabel.textContent = "Will update the shared variant only. No activation change.";
    setServerFeatureAvailability();
    return;
  }

  if (!worldId) {
    summaryLabel.textContent = "Will update shared variant and activate it after save. Choose a world first.";
    summaryLabel.classList.add("activation-save-summary__meta--warning");
    setServerFeatureAvailability();
    return;
  }

  summaryLabel.textContent = `Will update shared variant and activate it for ${scope}.`;
  setServerFeatureAvailability();
}

export function renderActivationMessage(message, tone = "info") {
  state.latestActivationPayload = null;
  state.activationRows = [];
  state.selectedActivationSelector = "";
  state.activationColumnWidths = null;
  updateCurrentObjectActivationState();
  syncActivationFilterOptions([]);
  setActivationFilterCount(0, 0);
  renderActivationTableMessage(message, tone);
  updateActivationStatusActionState();
  setServerFeatureAvailability();
}

function renderActivationTableMessage(message, tone = "info") {
  if (!dom.activationList) {
    return;
  }
  dom.activationList.innerHTML = "";
  const item = document.createElement("div");
  item.className = `report-item report-item--${tone}`;
  item.textContent = message;
  dom.activationList.appendChild(item);
}

function setActivationFilterCount(visibleCount, totalCount) {
  if (!dom.activationFilterCount) {
    return;
  }
  if (!totalCount) {
    dom.activationFilterCount.textContent = "Showing 0 mappings";
    return;
  }
  dom.activationFilterCount.textContent =
    visibleCount === totalCount
      ? `Showing ${visibleCount} mappings`
      : `Showing ${visibleCount} of ${totalCount} mappings`;
}

function getActivationRowBySelector(selector) {
  const normalizedSelector = String(selector || "").trim();
  if (!normalizedSelector) {
    return null;
  }
  return (
    (state.activationRows || []).find(
      (row) => String(row?.selector || "").trim() === normalizedSelector
    ) || null
  );
}

function getSelectedActivationRow() {
  return getActivationRowBySelector(state.selectedActivationSelector);
}

function setSelectedActivationRow(selector) {
  state.selectedActivationSelector = String(selector || "").trim();
  updateActivationStatusActionState();
}

function formatActivationRowLabel(row) {
  if (!row) {
    return "Selected mapping: none";
  }
  return `Selected mapping: ${row.policyId}:${row.variant}`;
}

function parseActivationPolicyId(policyIdValue) {
  const policyId = String(policyIdValue || "").trim();
  const parts = policyId.split(":");
  const policyType = String(parts.shift() || "").trim();
  const namespace = String(parts.shift() || "").trim();
  const policyKey = String(parts.join(":") || "").trim();
  return {
    policyId,
    policyType,
    namespace,
    policyKey,
  };
}

function normalizeActivationRows(items) {
  return (items || []).map((itemRow) => {
    const parsed = parseActivationPolicyId(itemRow?.policy_id);
    const variant = String(itemRow?.variant || "").trim();
    return {
      ...parsed,
      variant,
      selector: `${parsed.policyId}:${variant}`,
      status: "unknown",
      updatedAt: "",
      mappedAt: String(itemRow?.activated_at || "").trim(),
      activatedBy: String(itemRow?.activated_by || "").trim(),
      searchTarget: "",
    };
  });
}

const ACTIVATION_COLUMN_LABELS = [
  "Policy Type",
  "Namespace",
  "Policy Key",
  "Variant",
  "Status",
  "Updated At",
  "Activated By",
  "Mapped At",
];
const DEFAULT_ACTIVATION_COLUMN_WIDTHS = [90, 120, 300, 110, 100, 170, 140, 170];
let _measureCanvas = null;

function countValues(rows, selectValueFn) {
  const counts = new Map();
  for (const row of rows || []) {
    const value = String(selectValueFn(row) || "").trim();
    if (!value) {
      continue;
    }
    counts.set(value, (counts.get(value) || 0) + 1);
  }
  return counts;
}

function renderSelectOptionsWithCounts({
  selectElement,
  allLabel,
  countByValue,
}) {
  if (!selectElement) {
    return;
  }

  const previouslySelected = String(selectElement.value || "").trim();
  const entries = Array.from(countByValue.entries()).sort((left, right) =>
    left[0].localeCompare(right[0])
  );
  const totalCount = entries.reduce((acc, [, count]) => acc + count, 0);

  selectElement.innerHTML = "";
  const allOption = document.createElement("option");
  allOption.value = "";
  allOption.textContent = `${allLabel} (${totalCount})`;
  selectElement.appendChild(allOption);

  for (const [optionValue, count] of entries) {
    const option = document.createElement("option");
    option.value = optionValue;
    option.textContent = `${optionValue} (${count})`;
    selectElement.appendChild(option);
  }

  if (previouslySelected && countByValue.has(previouslySelected)) {
    selectElement.value = previouslySelected;
  }
}

function rowsForNamespaceCount(rows) {
  const selectedPolicyType = String(dom.activationFilterPolicyType?.value || "").trim();
  if (!selectedPolicyType) {
    return rows;
  }
  return rows.filter((row) => row.policyType === selectedPolicyType);
}

function rowsForStatusCount(rows) {
  const selectedPolicyType = String(dom.activationFilterPolicyType?.value || "").trim();
  const selectedNamespace = String(dom.activationFilterNamespace?.value || "").trim();
  return rows.filter((row) => {
    if (selectedPolicyType && row.policyType !== selectedPolicyType) {
      return false;
    }
    if (selectedNamespace && row.namespace !== selectedNamespace) {
      return false;
    }
    return true;
  });
}

function measureTextWidthPx(text, fontSpec) {
  if (!_measureCanvas) {
    _measureCanvas = document.createElement("canvas");
  }
  const context = _measureCanvas.getContext("2d");
  if (!context) {
    return String(text || "").length * 8;
  }
  context.font = fontSpec;
  return context.measureText(String(text || "")).width;
}

function activationColumnValues(row) {
  return [
    row.policyType || "--",
    row.namespace || "--",
    row.policyKey || "--",
    row.variant || "--",
    row.status || "--",
    row.updatedAt || "--",
    row.activatedBy || "--",
    row.mappedAt || "--",
  ];
}

function autosizeActivationColumnWidths(rows, containerWidthPx) {
  const labels = ACTIVATION_COLUMN_LABELS;
  const bodyFont = window.getComputedStyle(dom.activationList || document.body).font || "12px monospace";
  const widths = labels.map((label, index) => {
    let best = Math.ceil(measureTextWidthPx(label, bodyFont)) + 34;
    for (const row of rows) {
      const value = activationColumnValues(row)[index] || "";
      best = Math.max(best, Math.ceil(measureTextWidthPx(value, bodyFont)) + 20);
    }
    return best;
  });

  const totalWidth = widths.reduce((acc, value) => acc + value, 0);
  const targetWidth = Math.max(containerWidthPx || 0, totalWidth);
  if (!totalWidth || targetWidth <= totalWidth) {
    return widths;
  }
  const scale = targetWidth / totalWidth;
  return widths.map((value) => value * scale);
}

function getActivationColumnWidths(rows, containerWidthPx) {
  const existingWidths = Array.isArray(state.activationColumnWidths)
    ? state.activationColumnWidths
    : null;
  if (
    existingWidths &&
    existingWidths.length === ACTIVATION_COLUMN_LABELS.length &&
    existingWidths.every((value) => Number.isFinite(value) && value > 0)
  ) {
    return [...existingWidths];
  }
  return autosizeActivationColumnWidths(rows, containerWidthPx);
}

function applyActivationColumnWidths(table, columns, widths) {
  const normalizedWidths = widths.map((value, index) =>
    Number.isFinite(value) && value > 0 ? value : DEFAULT_ACTIVATION_COLUMN_WIDTHS[index]
  );
  const totalWidth = normalizedWidths.reduce((acc, value) => acc + value, 0);
  for (const [index, column] of columns.entries()) {
    column.style.width = `${normalizedWidths[index].toFixed(2)}px`;
  }
  table.style.width = `${Math.max(totalWidth, 1)}px`;
}

function syncActivationFilterOptions(rows) {
  renderSelectOptionsWithCounts({
    selectElement: dom.activationFilterPolicyType,
    allLabel: "All policy types",
    countByValue: countValues(rows, (row) => row.policyType),
  });
  renderSelectOptionsWithCounts({
    selectElement: dom.activationFilterNamespace,
    allLabel: "All namespaces",
    countByValue: countValues(rowsForNamespaceCount(rows), (row) => row.namespace),
  });
  renderSelectOptionsWithCounts({
    selectElement: dom.activationFilterStatus,
    allLabel: "All statuses",
    countByValue: countValues(rowsForStatusCount(rows), (row) => row.status),
  });
  if (dom.activationFilterSearch) {
    dom.activationFilterSearch.value = "";
  }
}

function filterActivationRows(rows) {
  const selectedPolicyType = String(dom.activationFilterPolicyType?.value || "").trim();
  const selectedNamespace = String(dom.activationFilterNamespace?.value || "").trim();
  const selectedStatus = String(dom.activationFilterStatus?.value || "").trim();
  const searchValue = String(dom.activationFilterSearch?.value || "")
    .trim()
    .toLowerCase();

  return rows.filter((row) => {
    if (selectedPolicyType && row.policyType !== selectedPolicyType) {
      return false;
    }
    if (selectedNamespace && row.namespace !== selectedNamespace) {
      return false;
    }
    if (selectedStatus && row.status !== selectedStatus) {
      return false;
    }
    if (searchValue && !row.searchTarget.includes(searchValue)) {
      return false;
    }
    return true;
  });
}

export function updateActivationStatusActionState() {
  const selectedRow = getSelectedActivationRow();
  if (dom.activationSelectedMapping) {
    dom.activationSelectedMapping.textContent = formatActivationRowLabel(selectedRow);
  }

  if (dom.activationSetStatus) {
    dom.activationSetStatus.disabled = !isServerAuthorized() || !selectedRow;
    if (!selectedRow) {
      dom.activationSetStatus.value = "";
      dom.activationSetStatus.dataset.boundSelector = "";
    } else if (dom.activationSetStatus.dataset.boundSelector !== selectedRow.selector) {
      const hasStatusOption = Array.from(dom.activationSetStatus.options || []).some(
        (option) => String(option.value || "").trim() === String(selectedRow.status || "").trim()
      );
      dom.activationSetStatus.value = hasStatusOption ? String(selectedRow.status || "").trim() : "";
      dom.activationSetStatus.dataset.boundSelector = selectedRow.selector;
    }
  }

  const selectedStatus = String(dom.activationSetStatus?.value || "").trim();
  const canApplyStatus =
    Boolean(selectedRow) &&
    isServerAuthorized() &&
    Boolean(selectedStatus) &&
    selectedStatus !== String(selectedRow?.status || "").trim();
  if (dom.btnActivationApplyStatus) {
    dom.btnActivationApplyStatus.disabled = !canApplyStatus;
  }
}

export async function applySelectedActivationStatus() {
  requireInventoryDeps();
  if (!isServerAuthorized()) {
    _setStatus("Status update unavailable: admin/superuser session required.");
    return;
  }

  const selectedRow = getSelectedActivationRow();
  if (!selectedRow) {
    _setStatus("Select a mapping row before applying a status change.");
    return;
  }

  const nextStatus = String(dom.activationSetStatus?.value || "").trim();
  if (!nextStatus) {
    _setStatus("Choose a target status before applying.");
    return;
  }
  if (nextStatus === String(selectedRow.status || "").trim()) {
    _setStatus(`Selected mapping is already ${nextStatus}.`);
    return;
  }

  _setStatus(`Applying status ${nextStatus} to ${selectedRow.policyId}:${selectedRow.variant}...`);
  try {
    const query = new URLSearchParams({ variant: selectedRow.variant });
    const detailPayload = await _fetchJson(
      sessionScopedUrl(`/api/policies/${encodeURIComponent(selectedRow.policyId)}?${query.toString()}`)
    );
    const savePayload = {
      policy_type: selectedRow.policyType,
      namespace: selectedRow.namespace,
      policy_key: selectedRow.policyKey,
      variant: selectedRow.variant,
      raw_content: JSON.stringify(detailPayload.content || {}, null, 2),
      schema_version: String(detailPayload.schema_version || "1.0").trim() || "1.0",
      status: nextStatus,
      activate: false,
    };

    const saveResult = await _fetchJson("/api/policy-save", {
      method: "POST",
      body: JSON.stringify(savePayload),
    });

    await refreshActivationScope({ silent: true });
    setSelectedActivationRow(selectedRow.selector);
    if (
      state.selectedPolicyRecord &&
      String(state.selectedPolicyRecord.policy_id || "").trim() === selectedRow.policyId &&
      String(state.selectedPolicyRecord.variant || "").trim() === selectedRow.variant
    ) {
      await loadPolicyObject(selectedRow.policyId, selectedRow.variant);
    }
    _setStatus(
      `Status updated for ${selectedRow.policyId}:${selectedRow.variant} to ${nextStatus} (v${saveResult.policy_version}).`
    );
  } catch (error) {
    _setStatus(`Status update failed: ${error.message}`);
  } finally {
    updateActivationStatusActionState();
    setServerFeatureAvailability();
  }
}

function renderActivationRowsTable(rows) {
  if (!dom.activationList) {
    return;
  }
  dom.activationList.innerHTML = "";

  const table = document.createElement("table");
  table.className = "inventory-table activation-table";
  table.setAttribute("aria-label", "Activation mappings table");

  const containerWidth = Math.max(dom.activationList.clientWidth || 0, 1);
  const columnWidths = getActivationColumnWidths(rows, containerWidth);
  const colgroup = document.createElement("colgroup");
  const columns = ACTIVATION_COLUMN_LABELS.map(() => {
    const col = document.createElement("col");
    colgroup.appendChild(col);
    return col;
  });
  applyActivationColumnWidths(table, columns, columnWidths);
  table.appendChild(colgroup);

  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  for (const [columnIndex, label] of ACTIVATION_COLUMN_LABELS.entries()) {
    const th = document.createElement("th");
    th.scope = "col";
    th.textContent = label;
    if (columnIndex < ACTIVATION_COLUMN_LABELS.length - 1) {
      const handle = document.createElement("span");
      handle.className = "activation-table__resize-handle";
      handle.setAttribute("aria-hidden", "true");
      handle.dataset.columnIndex = String(columnIndex);
      th.appendChild(handle);
      wireActivationColumnResize({
        handle,
        table,
        columns,
        columnIndex,
      });
    }
    headerRow.appendChild(th);
  }
  thead.appendChild(headerRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const row of rows) {
    const tr = document.createElement("tr");
    if (String(row.selector || "").trim() === String(state.selectedActivationSelector || "").trim()) {
      tr.classList.add("is-active");
    }
    tr.tabIndex = 0;
    tr.title = `${row.policyId}:${row.variant}`;
    tr.addEventListener("click", () => {
      setSelectedActivationRow(row.selector);
      applyActivationFilters();
    });
    tr.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }
      event.preventDefault();
      setSelectedActivationRow(row.selector);
      applyActivationFilters();
    });

    const columnValues = activationColumnValues(row);
    columnValues.forEach((value, index) => {
      const td = document.createElement("td");
      td.setAttribute("data-label", ACTIVATION_COLUMN_LABELS[index]);
      td.textContent = value;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  dom.activationList.appendChild(table);
  updateActivationStatusActionState();
}

function withActivationSearchTarget(row) {
  return {
    ...row,
    searchTarget: [
      row.policyId,
      row.policyType,
      row.namespace,
      row.policyKey,
      row.variant,
      row.status,
      row.updatedAt,
      row.activatedBy,
      row.mappedAt,
    ]
      .join(" ")
      .toLowerCase(),
  };
}

async function buildActivationStatusMap(rows) {
  const policyTypes = Array.from(
    new Set(
      (rows || [])
        .map((row) => String(row?.policyType || "").trim())
        .filter(Boolean)
    )
  );
  if (!policyTypes.length) {
    return new Map();
  }

  try {
    const payloadGroups = await Promise.all(
      policyTypes.map(async (policyType) => {
        const query = new URLSearchParams({ policy_type: policyType });
        const payload = await _fetchJson(
          sessionScopedUrl(`/api/policies?${query.toString()}`)
        );
        return Array.isArray(payload?.items) ? payload.items : [];
      })
    );

    const detailsBySelector = new Map();
    for (const group of payloadGroups) {
      for (const item of group) {
        const selector = `${String(item?.policy_id || "").trim()}:${String(item?.variant || "").trim()}`;
        const status = String(item?.status || "").trim();
        const updatedAt = String(item?.updated_at || "").trim();
        if (!selector || !status) {
          continue;
        }
        detailsBySelector.set(selector, {
          status,
          updatedAt,
        });
      }
    }
    return detailsBySelector;
  } catch (_error) {
    return new Map();
  }
}

function wireActivationColumnResize({
  handle,
  table,
  columns,
  columnIndex,
}) {
  handle.addEventListener("mousedown", (event) => {
    event.preventDefault();
    const startingWidths = columns.map((column) =>
      Math.max(column.getBoundingClientRect().width, parseFloat(column.style.width) || 0)
    );
    const startX = event.clientX;

    const onMouseMove = (moveEvent) => {
      const deltaX = moveEvent.clientX - startX;
      const leftWidth = startingWidths[columnIndex] + deltaX;
      const rightWidth = startingWidths[columnIndex + 1] - deltaX;
      if (leftWidth <= 0 || rightWidth <= 0) {
        return;
      }

      const nextWidths = [...startingWidths];
      nextWidths[columnIndex] = leftWidth;
      nextWidths[columnIndex + 1] = rightWidth;
      state.activationColumnWidths = nextWidths;
      applyActivationColumnWidths(table, columns, nextWidths);
    };

    const onMouseUp = () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  });
}

export function applyActivationFilters() {
  const allRows = Array.isArray(state.activationRows) ? state.activationRows : [];
  renderSelectOptionsWithCounts({
    selectElement: dom.activationFilterNamespace,
    allLabel: "All namespaces",
    countByValue: countValues(rowsForNamespaceCount(allRows), (row) => row.namespace),
  });
  renderSelectOptionsWithCounts({
    selectElement: dom.activationFilterStatus,
    allLabel: "All statuses",
    countByValue: countValues(rowsForStatusCount(allRows), (row) => row.status),
  });
  const sortedRows = [...allRows].sort((left, right) => {
    const leftSelector =
      `${left.policyType}:${left.namespace}:${left.policyKey}:${left.variant}`.toLowerCase();
    const rightSelector =
      `${right.policyType}:${right.namespace}:${right.policyKey}:${right.variant}`.toLowerCase();
    return leftSelector.localeCompare(rightSelector);
  });
  const filteredRows = filterActivationRows(sortedRows);
  const selectedSelector = String(state.selectedActivationSelector || "").trim();
  if (
    selectedSelector &&
    !filteredRows.some((row) => String(row?.selector || "").trim() === selectedSelector)
  ) {
    state.selectedActivationSelector = "";
  }
  setActivationFilterCount(filteredRows.length, sortedRows.length);

  if (!sortedRows.length) {
    renderActivationTableMessage("No active mappings for this scope yet.");
    updateActivationStatusActionState();
    return;
  }
  if (!filteredRows.length) {
    renderActivationTableMessage("No mappings matched current filters.", "warning");
    updateActivationStatusActionState();
    return;
  }
  renderActivationRowsTable(filteredRows);
}

async function renderActivationScopePayload(payload) {
  state.latestActivationPayload = payload;
  state.activationColumnWidths = null;
  const baseRows = normalizeActivationRows(
    Array.isArray(payload?.items) ? payload.items : []
  );
  const detailsBySelector = await buildActivationStatusMap(baseRows);
  state.activationRows = baseRows.map((row) =>
    withActivationSearchTarget({
      ...row,
      status: detailsBySelector.get(row.selector)?.status || "unknown",
      updatedAt: detailsBySelector.get(row.selector)?.updatedAt || "",
    })
  );
  updateCurrentObjectActivationState();
  syncActivationFilterOptions(state.activationRows);
  applyActivationFilters();
  setServerFeatureAvailability();
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
    renderActivationMessage("Select a world before loading activation mappings.", "warning");
    if (!silent) {
      _setStatus("Activation mapping load skipped: world selection is required.");
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
    await renderActivationScopePayload(payload);
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
  state.editorIsEditing = false;
  state.editorBaseContent = "";
  setEditorReadOnlyMode(true);
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
