import { dom } from "./dom.js";

let _fetchJson = null;
let _setStatus = null;

export function configureValidation({ fetchJson, setStatus }) {
  _fetchJson = fetchJson;
  _setStatus = setStatus;
}

function requireValidationDeps() {
  if (!_fetchJson || !_setStatus) {
    throw new Error("Validation helpers are not configured.");
  }
}

function renderValidation(report) {
  const sourceKind = report.source_kind || "local_mirror_snapshot";
  dom.validationCounts.textContent =
    `errors=${report.counts.error} warnings=${report.counts.warning} info=${report.counts.info} source=${sourceKind}`;

  dom.validationList.innerHTML = "";
  if (!report.issues.length) {
    const item = document.createElement("li");
    item.className = "report-item report-item--info";
    item.textContent = "No validation issues.";
    dom.validationList.appendChild(item);
    return;
  }

  for (const issue of report.issues) {
    const item = document.createElement("li");
    item.className = `report-item report-item--${issue.level}`;
    const location = issue.relative_path || "<root>";
    item.textContent = `[${issue.level.toUpperCase()}] ${issue.code} ${location}\n${issue.message}`;
    dom.validationList.appendChild(item);
  }
}

export async function runValidation() {
  requireValidationDeps();
  _setStatus("Running local mirror validation diagnostics (non-authoritative)...");
  try {
    const report = await _fetchJson("/api/validate");
    renderValidation(report);
    const canonicalAuthority = report.canonical_authority || "mud_server_policy_api";
    _setStatus(`Mirror validation diagnostics complete. Canonical authority: ${canonicalAuthority}.`);
  } catch (error) {
    _setStatus(`Mirror validation failed: ${error.message}`);
  }
}
