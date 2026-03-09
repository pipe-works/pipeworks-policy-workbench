const dom = {
  treeSummary: document.getElementById("tree-summary"),
  treeList: document.getElementById("tree-list"),
  editorPath: document.getElementById("editor-path"),
  fileEditor: document.getElementById("file-editor"),
  validationCounts: document.getElementById("validation-counts"),
  validationList: document.getElementById("validation-list"),
  syncCounts: document.getElementById("sync-counts"),
  syncList: document.getElementById("sync-list"),
  statusText: document.getElementById("status-text"),
  btnRefreshTree: document.getElementById("btn-refresh-tree"),
  btnSaveFile: document.getElementById("btn-save-file"),
  btnReloadFile: document.getElementById("btn-reload-file"),
  btnRunValidation: document.getElementById("btn-run-validation"),
  btnBuildSync: document.getElementById("btn-build-sync"),
  btnApplySync: document.getElementById("btn-apply-sync"),
};

const state = {
  selectedPath: "",
  fileIndex: [],
  sourceRoot: "",
  directoriesCount: 0,
};

function setStatus(message) {
  dom.statusText.textContent = message;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {
      // Use fallback detail.
    }
    throw new Error(detail);
  }

  return response.json();
}

function renderTree(artifacts, sourceRoot, directoriesCount) {
  state.fileIndex = artifacts;
  state.sourceRoot = sourceRoot;
  state.directoriesCount = directoriesCount;
  dom.treeSummary.textContent = `source=${sourceRoot} directories=${directoriesCount} files=${artifacts.length}`;

  dom.treeList.innerHTML = "";
  for (const artifact of artifacts) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.className = "tree-item";
    if (artifact.relative_path === state.selectedPath) {
      button.classList.add("is-active");
    }

    const pathSpan = document.createElement("span");
    pathSpan.className = "tree-item__path";
    pathSpan.textContent = artifact.relative_path;

    const roleSpan = document.createElement("span");
    roleSpan.className = "tree-item__role";
    roleSpan.textContent = artifact.role;

    button.append(pathSpan, roleSpan);
    button.addEventListener("click", () => loadFile(artifact.relative_path));

    item.appendChild(button);
    dom.treeList.appendChild(item);
  }
}

function renderValidation(report) {
  dom.validationCounts.textContent =
    `errors=${report.counts.error} warnings=${report.counts.warning} info=${report.counts.info}`;

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

function renderSyncPlan(plan) {
  dom.syncCounts.textContent =
    `create=${plan.counts.create} update=${plan.counts.update} ` +
    `unchanged=${plan.counts.unchanged} delete_candidate=${plan.counts.delete_candidate}`;

  dom.syncList.innerHTML = "";
  if (!plan.actions.length) {
    const item = document.createElement("li");
    item.className = "report-item report-item--info";
    item.textContent = "No sync actions.";
    dom.syncList.appendChild(item);
    return;
  }

  for (const action of plan.actions) {
    const item = document.createElement("li");
    const severity = action.action === "delete_candidate" ? "warning" : "info";
    item.className = `report-item report-item--${severity}`;
    const reason = action.reason ? ` (${action.reason})` : "";
    item.textContent = `[${action.target}] ${action.action} ${action.relative_path}${reason}`;
    dom.syncList.appendChild(item);
  }
}

async function loadTree() {
  setStatus("Loading policy tree...");
  try {
    const payload = await fetchJson("/api/tree");
    renderTree(payload.artifacts, payload.source_root, payload.directories.length);
    setStatus("Policy tree loaded.");
  } catch (error) {
    setStatus(`Tree load failed: ${error.message}`);
  }
}

async function loadFile(relativePath) {
  state.selectedPath = relativePath;
  dom.editorPath.textContent = relativePath;
  setStatus(`Loading ${relativePath}...`);

  try {
    const payload = await fetchJson(
      `/api/file?relative_path=${encodeURIComponent(relativePath)}`
    );
    dom.fileEditor.value = payload.content;
    renderTree(state.fileIndex, state.sourceRoot, state.directoriesCount);
    setStatus(`Loaded ${relativePath}.`);
  } catch (error) {
    setStatus(`File load failed: ${error.message}`);
  }
}

async function saveCurrentFile() {
  if (!state.selectedPath) {
    setStatus("Select a file before saving.");
    return;
  }

  setStatus(`Saving ${state.selectedPath}...`);
  try {
    await fetchJson("/api/file", {
      method: "PUT",
      body: JSON.stringify({
        relative_path: state.selectedPath,
        content: dom.fileEditor.value,
      }),
    });
    setStatus(`Saved ${state.selectedPath}.`);
  } catch (error) {
    setStatus(`Save failed: ${error.message}`);
  }
}

async function reloadCurrentFile() {
  if (!state.selectedPath) {
    setStatus("Select a file before reloading.");
    return;
  }
  await loadFile(state.selectedPath);
}

async function runValidation() {
  setStatus("Running validation...");
  try {
    const report = await fetchJson("/api/validate");
    renderValidation(report);
    setStatus("Validation complete.");
  } catch (error) {
    setStatus(`Validation failed: ${error.message}`);
  }
}

async function buildSyncPlan() {
  setStatus("Building sync plan...");
  try {
    const plan = await fetchJson("/api/sync-plan?include_unchanged=false");
    renderSyncPlan(plan);
    setStatus("Sync plan ready.");
  } catch (error) {
    setStatus(`Sync plan failed: ${error.message}`);
  }
}

async function applySyncPlan() {
  if (!window.confirm("Apply create/update sync actions? Delete candidates are not removed.")) {
    return;
  }

  setStatus("Applying sync plan...");
  try {
    const result = await fetchJson("/api/sync-apply", {
      method: "POST",
      body: JSON.stringify({ confirm: true }),
    });
    setStatus(
      `Sync apply complete: created=${result.created} updated=${result.updated} skipped=${result.skipped}`
    );
    await buildSyncPlan();
  } catch (error) {
    setStatus(`Sync apply failed: ${error.message}`);
  }
}

async function init() {
  dom.btnRefreshTree.addEventListener("click", loadTree);
  dom.btnSaveFile.addEventListener("click", saveCurrentFile);
  dom.btnReloadFile.addEventListener("click", reloadCurrentFile);
  dom.btnRunValidation.addEventListener("click", runValidation);
  dom.btnBuildSync.addEventListener("click", buildSyncPlan);
  dom.btnApplySync.addEventListener("click", applySyncPlan);

  await loadTree();
  await runValidation();
  await buildSyncPlan();
}

init();
