import { dom } from "../dom.js";
import { state } from "../state.js";

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

export function renderActivationTableMessage(message, tone = "info") {
  if (!dom.activationList) {
    return;
  }
  dom.activationList.innerHTML = "";
  const item = document.createElement("div");
  item.className = `report-item report-item--${tone}`;
  item.textContent = message;
  dom.activationList.appendChild(item);
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
  const bodyFont = window.getComputedStyle(dom.activationList || document.body).font || "12px monospace";
  const widths = ACTIVATION_COLUMN_LABELS.map((label, index) => {
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
    existingWidths
    && existingWidths.length === ACTIVATION_COLUMN_LABELS.length
    && existingWidths.every((value) => Number.isFinite(value) && value > 0)
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

export function renderActivationRowsTable(rows, { onSelectRow }) {
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
      onSelectRow(row.selector);
    });
    tr.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }
      event.preventDefault();
      onSelectRow(row.selector);
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
}
