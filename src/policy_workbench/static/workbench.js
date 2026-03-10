const dom = {
  treeSummaryDirectories: document.getElementById("tree-summary-directories"),
  treeSummaryFiles: document.getElementById("tree-summary-files"),
  treeList: document.getElementById("tree-list"),
  editorPath: document.getElementById("editor-path"),
  fileEditor: document.getElementById("file-editor"),
  themeToggle: document.getElementById("theme-toggle"),
  validationCounts: document.getElementById("validation-counts"),
  validationList: document.getElementById("validation-list"),
  syncCounts: document.getElementById("sync-counts"),
  syncList: document.getElementById("sync-list"),
  statusText: document.getElementById("status-text"),
  statusSource: document.getElementById("status-source"),
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

const THEME_STORAGE_KEY = "ppw-theme";

function setStatus(message) {
  dom.statusText.textContent = message;
}

function wireThemeToggle() {
  const button = dom.themeToggle;
  if (!button) {
    return;
  }

  const applyTheme = (theme) => {
    const normalizedTheme = theme === "light" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", normalizedTheme);
    button.textContent = normalizedTheme === "light" ? "\u263E Dark" : "\u2600 Light";

    try {
      localStorage.setItem(THEME_STORAGE_KEY, normalizedTheme);
    } catch {
      // Theme persistence is optional; UI still works without storage access.
    }
  };

  let savedTheme = "dark";
  try {
    savedTheme = localStorage.getItem(THEME_STORAGE_KEY) || "dark";
  } catch {
    // Fall back to default theme when storage is unavailable.
  }
  applyTheme(savedTheme);

  button.addEventListener("click", () => {
    const currentTheme = document.documentElement.getAttribute("data-theme") || "dark";
    applyTheme(currentTheme === "dark" ? "light" : "dark");
  });
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
  dom.treeSummaryDirectories.textContent = `${directoriesCount}`;
  dom.treeSummaryFiles.textContent = `${artifacts.length}`;
  if (dom.statusSource) {
    dom.statusSource.textContent = `source: ${sourceRoot}`;
    dom.statusSource.title = sourceRoot;
  }

  dom.treeList.innerHTML = "";
  if (!artifacts.length) {
    const emptyItem = document.createElement("li");
    emptyItem.className = "report-item report-item--info";
    emptyItem.textContent = "No editable .txt/.yaml/.yml policy files found.";
    dom.treeList.appendChild(emptyItem);
    return;
  }

  const groupedArtifacts = groupArtifactsByDirectory(artifacts);
  for (const [directory, directoryArtifacts] of groupedArtifacts) {
    const groupItem = document.createElement("li");
    groupItem.className = "tree-group";

    const details = document.createElement("details");
    details.className = "tree-group__details";
    details.open = true;

    const summary = document.createElement("summary");
    summary.className = "tree-group__summary";
    const label = document.createElement("span");
    label.className = "tree-group__label";
    label.textContent = directory;
    const count = document.createElement("span");
    count.className = "tree-group__count";
    count.textContent = `${directoryArtifacts.length}`;
    summary.append(label, count);

    const filesList = document.createElement("ul");
    filesList.className = "tree-group__files";

    for (const artifact of directoryArtifacts) {
      const fileItem = document.createElement("li");
      const button = document.createElement("button");
      button.className = "tree-item tree-item--leaf";
      if (artifact.relative_path === state.selectedPath) {
        button.classList.add("is-active");
      }
      button.title = artifact.relative_path;

      const pathSpan = document.createElement("span");
      pathSpan.className = "tree-item__path";
      pathSpan.textContent = basenameFromPath(artifact.relative_path);

      const roleSpan = document.createElement("span");
      roleSpan.className = "tree-item__role";
      roleSpan.textContent = artifact.role;

      button.append(pathSpan, roleSpan);
      button.addEventListener("click", () => loadFile(artifact.relative_path));

      fileItem.appendChild(button);
      filesList.appendChild(fileItem);
    }

    details.append(summary, filesList);
    groupItem.appendChild(details);
    dom.treeList.appendChild(groupItem);
  }
}

function groupArtifactsByDirectory(artifacts) {
  const byDirectory = new Map();
  for (const artifact of artifacts) {
    const directory = directoryFromPath(artifact.relative_path);
    if (!byDirectory.has(directory)) {
      byDirectory.set(directory, []);
    }
    byDirectory.get(directory).push(artifact);
  }

  return [...byDirectory.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([directory, directoryArtifacts]) => [
      directory,
      [...directoryArtifacts].sort((left, right) =>
        left.relative_path.localeCompare(right.relative_path)
      ),
    ]);
}

function directoryFromPath(relativePath) {
  const lastSeparatorIndex = relativePath.lastIndexOf("/");
  if (lastSeparatorIndex === -1) {
    return "<root>";
  }
  return relativePath.slice(0, lastSeparatorIndex);
}

function basenameFromPath(relativePath) {
  const lastSeparatorIndex = relativePath.lastIndexOf("/");
  if (lastSeparatorIndex === -1) {
    return relativePath;
  }
  return relativePath.slice(lastSeparatorIndex + 1);
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
  wireThemeToggle();
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
