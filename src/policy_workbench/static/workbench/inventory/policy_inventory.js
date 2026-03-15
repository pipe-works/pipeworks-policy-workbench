import { dom } from "../dom.js";
import { state } from "../state.js";
import { isServerAuthorized, sessionScopedUrl } from "../runtime.js";
import { fetchJson, requireInventoryDeps, setStatus } from "./context.js";
import { renderPolicyStatusOptionCounts } from "./policy_filters.js";
import { buildPolicySelectorLabel } from "./policy_selector.js";
import { setEditorFromPolicyRecord } from "./policy_object.js";

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

function selectedPolicyKey() {
  if (!state.selectedPolicyRecord) {
    return "";
  }
  return `${state.selectedPolicyRecord.policy_id}:${state.selectedPolicyRecord.variant}`;
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
    const payload = await fetchJson(sessionScopedUrl(`/api/policies${suffix}`));
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
    setStatus("Policy inventory requires an admin/superuser session.");
    return;
  }
  setStatus("Loading API-first policy inventory...");
  try {
    await refreshPolicyStatusCounts();
    const query = buildPolicyInventoryQueryString();
    const suffix = query ? `?${query}` : "";
    const payload = await fetchJson(sessionScopedUrl(`/api/policies${suffix}`));
    renderPolicyInventory(payload.items || []);
    setStatus(`Policy inventory loaded (${payload.item_count || 0} items).`);
  } catch (error) {
    setStatus(`Policy inventory load failed: ${error.message}`);
  }
}

export async function loadPolicyObject(policyId, variant = "") {
  requireInventoryDeps();
  if (!isServerAuthorized()) {
    setStatus("Cannot load policy object: admin/superuser session required.");
    return;
  }
  setStatus(`Loading policy object ${policyId}:${variant || "latest"}...`);
  try {
    const query = new URLSearchParams();
    if ((variant || "").trim()) {
      query.set("variant", variant.trim());
    }
    const suffix = query.toString() ? `?${query.toString()}` : "";
    const payload = await fetchJson(
      sessionScopedUrl(`/api/policies/${encodeURIComponent(policyId)}${suffix}`)
    );
    setEditorFromPolicyRecord(payload);
    renderPolicyInventory(state.inventoryItems);
    if (state.selectedArtifact?.is_authorable) {
      setStatus(`Loaded ${payload.policy_id}:${payload.variant} from mud-server API.`);
    } else {
      setStatus(
        `Loaded ${payload.policy_id}:${payload.variant} from mud-server API (read-only: save not yet supported for ${payload.policy_type}).`
      );
    }
  } catch (error) {
    setStatus(`Policy object load failed: ${error.message}`);
  }
}
