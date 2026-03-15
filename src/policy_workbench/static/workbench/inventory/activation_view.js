import { dom } from "../dom.js";
import { state } from "../state.js";
import { isServerAuthorized, setServerFeatureAvailability } from "../runtime.js";
import { updateCurrentObjectActivationState } from "./policy_object.js";
import { renderActivationRowsTable, renderActivationTableMessage } from "./activation_table.js";

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

export function getSelectedActivationRow() {
  return getActivationRowBySelector(state.selectedActivationSelector);
}

export function setSelectedActivationRow(selector) {
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

export function normalizeActivationRows(items) {
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

export function syncActivationFilterOptions(rows) {
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
    Boolean(selectedRow)
    && isServerAuthorized()
    && Boolean(selectedStatus)
    && selectedStatus !== String(selectedRow?.status || "").trim();
  if (dom.btnActivationApplyStatus) {
    dom.btnActivationApplyStatus.disabled = !canApplyStatus;
  }
}

export function withActivationSearchTarget(row) {
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
    selectedSelector
    && !filteredRows.some((row) => String(row?.selector || "").trim() === selectedSelector)
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
  renderActivationRowsTable(filteredRows, {
    onSelectRow: (selector) => {
      setSelectedActivationRow(selector);
      applyActivationFilters();
    },
  });
  updateActivationStatusActionState();
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
