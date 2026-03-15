import { dom } from "../dom.js";
import { state } from "../state.js";
import { isServerAuthorized, sessionScopedUrl } from "../runtime.js";
import { fetchJson, requireInventoryDeps, setStatus } from "./context.js";
import { updateActivationStatusActionState } from "./activation_view.js";

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

export function renderPolicyStatusOptionCounts(statusCounts = new Map()) {
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

async function refreshPolicyTypeOptions({ silent = true } = {}) {
  requireInventoryDeps();
  try {
    const payload = await fetchJson(sessionScopedUrl("/api/policy-types"));
    renderPolicyTypeOptions(payload);
    if (!silent && payload?.detail) {
      setStatus(payload.detail);
    }
  } catch (error) {
    renderPolicyTypeOptions({ items: [] });
    if (!silent) {
      setStatus(`Policy type options load failed: ${error.message}`);
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
    const payload = await fetchJson(sessionScopedUrl(`/api/policy-namespaces${suffix}`));
    renderPolicyNamespaceOptions(payload);
    if (!silent && payload?.detail) {
      setStatus(payload.detail);
    }
  } catch (error) {
    renderPolicyNamespaceOptions({ items: [] });
    if (!silent) {
      setStatus(`Policy namespace options load failed: ${error.message}`);
    }
  }
}

async function refreshPolicyStatusOptions({ silent = true } = {}) {
  requireInventoryDeps();
  try {
    const payload = await fetchJson(sessionScopedUrl("/api/policy-statuses"));
    renderPolicyStatusOptions(payload);
    if (!silent && payload?.detail) {
      setStatus(payload.detail);
    }
  } catch (error) {
    renderPolicyStatusOptions({ items: [] });
    if (!silent) {
      setStatus(`Policy status options load failed: ${error.message}`);
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
