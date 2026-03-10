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
  syncPlanState: document.getElementById("sync-plan-state"),
  syncList: document.getElementById("sync-list"),
  syncDiffModal: document.getElementById("sync-diff-modal"),
  syncDiffBackdrop: document.getElementById("sync-diff-backdrop"),
  syncDiffClose: document.getElementById("sync-diff-close"),
  syncDiffCloseX: document.getElementById("sync-diff-close-x"),
  syncDiffTitle: document.getElementById("sync-diff-title"),
  syncDiffMeta: document.getElementById("sync-diff-meta"),
  syncComparePath: document.getElementById("sync-compare-path"),
  syncCompareCopyPath: document.getElementById("sync-compare-copy-path"),
  syncCompareColumns: document.getElementById("sync-compare-columns"),
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
  currentComparePath: "",
  currentCompareRelativePath: "",
  syncPlanBuiltAt: null,
  syncPlanIsStale: true,
  syncRequestInFlight: false,
  compareContentElements: [],
  syncedCompareIds: new Set(),
  isSyncScrolling: false,
};

const THEME_STORAGE_KEY = "ppw-theme";
const SYNC_REFRESH_LABEL = "Refresh Dry-Run Plan";
const SYNC_APPLY_LABEL = "Apply Create/Update";

function setStatus(message) {
  dom.statusText.textContent = message;
}

function setEditorReadOnlyMode(isReadOnly) {
  dom.fileEditor.readOnly = isReadOnly;
  dom.fileEditor.classList.toggle("is-readonly", isReadOnly);
  dom.btnSaveFile.disabled = isReadOnly;
  dom.btnReloadFile.disabled = isReadOnly;
}

function formatLocalDateTime(dateValue) {
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(dateValue);
}

function updateSyncPlanStateLine() {
  if (!dom.syncPlanState) {
    return;
  }

  if (!state.syncPlanBuiltAt) {
    dom.syncPlanState.textContent = "plan: not generated yet";
    return;
  }

  const builtText = formatLocalDateTime(state.syncPlanBuiltAt);
  if (state.syncPlanIsStale) {
    dom.syncPlanState.textContent = `plan: stale | last generated ${builtText}`;
    return;
  }

  dom.syncPlanState.textContent = `plan: fresh | generated ${builtText}`;
}

function markSyncPlanStale() {
  state.syncPlanIsStale = true;
  updateSyncPlanStateLine();
}

function setSyncButtonsBusy(isBusy, mode = "") {
  state.syncRequestInFlight = isBusy;

  if (!dom.btnBuildSync || !dom.btnApplySync) {
    return;
  }

  dom.btnBuildSync.disabled = isBusy;
  dom.btnApplySync.disabled = isBusy;
  dom.btnBuildSync.textContent = isBusy && mode === "build" ? "Refreshing..." : SYNC_REFRESH_LABEL;
  dom.btnApplySync.textContent = isBusy && mode === "apply" ? "Applying..." : SYNC_APPLY_LABEL;
  dom.btnBuildSync.setAttribute("aria-busy", isBusy && mode === "build" ? "true" : "false");
  dom.btnApplySync.setAttribute("aria-busy", isBusy && mode === "apply" ? "true" : "false");
}

async function fetchSyncPlan(includeUnchanged = false) {
  return fetchJson(`/api/sync-plan?include_unchanged=${includeUnchanged}`);
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
  const visibleCounts = {
    create: 0,
    update: 0,
    unchanged: 0,
    delete_candidate: 0,
  };
  for (const action of plan.actions) {
    if (Object.prototype.hasOwnProperty.call(visibleCounts, action.action)) {
      visibleCounts[action.action] += 1;
    }
  }

  dom.syncCounts.textContent =
    `visible: create=${visibleCounts.create} update=${visibleCounts.update} ` +
    `unchanged=${visibleCounts.unchanged} delete_candidate=${visibleCounts.delete_candidate} | ` +
    `total: create=${plan.counts.create} update=${plan.counts.update} ` +
    `unchanged=${plan.counts.unchanged} delete_candidate=${plan.counts.delete_candidate}`;

  state.syncPlanBuiltAt = new Date();
  state.syncPlanIsStale = false;
  updateSyncPlanStateLine();

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
    const button = document.createElement("button");
    button.className = "sync-action-button";
    button.type = "button";
    button.textContent = `[${action.target}] ${action.action} ${action.relative_path}${reason}`;
    button.title = "Open source/targets side-by-side compare";
    button.addEventListener("click", () => showSyncCompare(action));
    item.appendChild(button);
    dom.syncList.appendChild(item);
  }
}

function closeSyncDiffModal() {
  if (!dom.syncDiffModal) {
    return;
  }
  dom.syncDiffModal.classList.add("hidden");
}

function openSyncDiffModal() {
  if (!dom.syncDiffModal) {
    return;
  }
  dom.syncDiffModal.classList.remove("hidden");
}

async function showSyncCompare(action) {
  if (!dom.syncDiffTitle || !dom.syncDiffMeta || !dom.syncCompareColumns || !dom.syncComparePath) {
    setStatus("Diff modal is unavailable in the current page template.");
    return;
  }

  setStatus(`Loading compare view for ${action.relative_path}...`);

  try {
    const payload = await fetchJson(
      `/api/sync-compare?relative_path=${encodeURIComponent(action.relative_path)}&focus_target=${encodeURIComponent(action.target)}`
    );
    dom.syncDiffTitle.textContent = `Sync Compare · ${payload.relative_path}`;
    dom.syncDiffMeta.textContent =
      `Canonical source compared with ${payload.variants.length - 1} target repos. ` +
      `Unique content variants: ${payload.unique_variant_count}.`;
    state.currentCompareRelativePath = payload.relative_path;
    state.currentComparePath = `pipeworks_web/policies/${payload.relative_path}`;
    dom.syncComparePath.textContent = formatMiddleTruncatedPath(state.currentComparePath, 72);
    dom.syncComparePath.title = state.currentComparePath;
    renderSyncCompareColumns(payload.variants);
    openSyncDiffModal();
    setStatus(`Compare view loaded for ${action.relative_path}.`);
  } catch (error) {
    setStatus(`Compare load failed: ${error.message}`);
  }
}

function renderSyncCompareColumns(variants) {
  if (!dom.syncCompareColumns) {
    return;
  }

  dom.syncCompareColumns.innerHTML = "";
  state.compareContentElements = [];
  state.syncedCompareIds = new Set();
  state.isSyncScrolling = false;

  const sourceIndex = variants.findIndex((variant) => variant.kind === "source");
  const canonicalIndex = sourceIndex >= 0 ? sourceIndex : 0;
  const canonicalVariant = variants[canonicalIndex];
  const canonicalLines = splitLinesForCompare(canonicalVariant.content || "");

  const canonicalChangedLines = new Set();
  const changedByVariantIndex = new Map();
  variants.forEach((variant, index) => {
    if (index === canonicalIndex) {
      return;
    }
    if (!variant.exists) {
      canonicalLines.forEach((_, canonicalLineIndex) => {
        canonicalChangedLines.add(canonicalLineIndex);
      });
      changedByVariantIndex.set(index, new Set([0]));
      return;
    }

    const variantLines = splitLinesForCompare(variant.content || "");
    const { baseChanged, otherChanged } = buildChangedLineSets(canonicalLines, variantLines);
    baseChanged.forEach((lineIndex) => canonicalChangedLines.add(lineIndex));
    changedByVariantIndex.set(index, otherChanged);
  });

  variants.forEach((variant, index) => {
    const card = document.createElement("article");
    card.className = "sync-compare-card";

    const header = document.createElement("header");
    header.className = "sync-compare-card__header";

    const title = document.createElement("span");
    title.className = "sync-compare-card__title";
    title.textContent = variant.label;

    const badges = document.createElement("div");
    badges.className = "sync-compare-card__badges";
    badges.append(
      buildCompareBadge(`variant ${variant.group_id}`, "muted"),
      buildCompareBadge(variant.kind, "info"),
      buildCompareBadge(compareStatusLabel(variant), variant.matches_source ? "ok" : "warn")
    );
    if (variant.action) {
      badges.append(buildCompareBadge(variant.action, "muted"));
    }

    const compareId = `compare-${index}`;
    const actions = document.createElement("div");
    actions.className = "sync-compare-card__actions";

    const openButton = document.createElement("button");
    openButton.type = "button";
    openButton.className = "btn btn--secondary btn--sm";
    openButton.textContent = "Open";
    openButton.title = "Open this variant in the main editor";
    openButton.addEventListener("click", () => {
      void openCompareVariantInEditor(variant);
    });

    const syncLabel = document.createElement("label");
    syncLabel.className = "sync-compare-card__sync";
    const syncToggle = document.createElement("input");
    syncToggle.className = "sync-compare-card__sync-toggle";
    syncToggle.type = "checkbox";
    syncToggle.checked = true;
    syncToggle.dataset.compareId = compareId;
    const syncText = document.createElement("span");
    syncText.textContent = "Sync scroll";
    syncLabel.append(syncToggle, syncText);

    syncToggle.addEventListener("change", () => {
      if (syncToggle.checked) {
        state.syncedCompareIds.add(compareId);
      } else {
        state.syncedCompareIds.delete(compareId);
      }
    });

    actions.append(openButton, syncLabel);
    header.append(title, badges, actions);

    const content = document.createElement("div");
    content.className = "sync-compare-card__content";
    content.dataset.compareId = compareId;
    const changedLineSet = index === canonicalIndex
      ? canonicalChangedLines
      : (changedByVariantIndex.get(index) || new Set());
    const contentText = variant.exists ? variant.content || "" : "<missing file>";
    renderHighlightedContent(
      content,
      contentText,
      changedLineSet,
      index === canonicalIndex ? "source" : "target"
    );

    state.compareContentElements.push(content);
    state.syncedCompareIds.add(compareId);
    content.addEventListener("scroll", () => handleCompareContentScroll(compareId, content));

    card.append(header, content);
    dom.syncCompareColumns.appendChild(card);
  });
}

async function openCompareVariantInEditor(variant) {
  const relativePath = state.currentCompareRelativePath;
  const displayPath = state.currentComparePath || relativePath || "<unknown path>";
  if (!relativePath) {
    setStatus("Cannot open compare variant because no path is loaded.");
    return;
  }

  if (variant.kind === "source") {
    setEditorReadOnlyMode(false);
    await loadFile(relativePath);
    closeSyncDiffModal();
    return;
  }

  state.selectedPath = "";
  setEditorReadOnlyMode(true);
  dom.editorPath.textContent = `${variant.label} (read-only)`;
  dom.editorPath.title = `${variant.label}: ${displayPath}`;
  dom.fileEditor.value = variant.exists ? variant.content || "" : "<missing file>";
  closeSyncDiffModal();
  setStatus(`Opened ${variant.label} snapshot (${displayPath}) in read-only mode.`);
}

function splitLinesForCompare(content) {
  return content.replaceAll("\r\n", "\n").replaceAll("\r", "\n").split("\n");
}

function buildChangedLineSets(baseLines, otherLines) {
  const baseLength = baseLines.length;
  const otherLength = otherLines.length;

  const matrix = Array.from({ length: baseLength + 1 }, () => Array(otherLength + 1).fill(0));
  for (let baseIndex = 1; baseIndex <= baseLength; baseIndex += 1) {
    for (let otherIndex = 1; otherIndex <= otherLength; otherIndex += 1) {
      if (baseLines[baseIndex - 1] === otherLines[otherIndex - 1]) {
        matrix[baseIndex][otherIndex] = matrix[baseIndex - 1][otherIndex - 1] + 1;
      } else {
        matrix[baseIndex][otherIndex] = Math.max(
          matrix[baseIndex - 1][otherIndex],
          matrix[baseIndex][otherIndex - 1]
        );
      }
    }
  }

  const baseChanged = new Set();
  const otherChanged = new Set();
  let baseIndex = baseLength;
  let otherIndex = otherLength;
  while (baseIndex > 0 && otherIndex > 0) {
    if (baseLines[baseIndex - 1] === otherLines[otherIndex - 1]) {
      baseIndex -= 1;
      otherIndex -= 1;
      continue;
    }

    if (matrix[baseIndex - 1][otherIndex] >= matrix[baseIndex][otherIndex - 1]) {
      baseChanged.add(baseIndex - 1);
      baseIndex -= 1;
      continue;
    }

    otherChanged.add(otherIndex - 1);
    otherIndex -= 1;
  }

  while (baseIndex > 0) {
    baseChanged.add(baseIndex - 1);
    baseIndex -= 1;
  }
  while (otherIndex > 0) {
    otherChanged.add(otherIndex - 1);
    otherIndex -= 1;
  }

  return { baseChanged, otherChanged };
}

function renderHighlightedContent(container, content, changedLineSet, tone) {
  container.innerHTML = "";
  const lines = splitLinesForCompare(content);

  lines.forEach((line, lineIndex) => {
    const lineNode = document.createElement("div");
    lineNode.className = "sync-compare-line";
    if (changedLineSet.has(lineIndex)) {
      lineNode.classList.add("sync-compare-line--changed");
      lineNode.classList.add(`sync-compare-line--changed-${tone}`);
    }
    lineNode.textContent = line.length ? line : " ";
    container.appendChild(lineNode);
  });
}

function handleCompareContentScroll(sourceId, sourceElement) {
  if (state.isSyncScrolling || !state.syncedCompareIds.has(sourceId)) {
    return;
  }

  const syncedElements = state.compareContentElements.filter((element) =>
    state.syncedCompareIds.has(element.dataset.compareId || "")
  );
  if (syncedElements.length < 2) {
    return;
  }

  const sourceVerticalMax = sourceElement.scrollHeight - sourceElement.clientHeight;
  const sourceHorizontalMax = sourceElement.scrollWidth - sourceElement.clientWidth;
  const verticalRatio = sourceVerticalMax > 0 ? sourceElement.scrollTop / sourceVerticalMax : 0;
  const horizontalRatio = sourceHorizontalMax > 0 ? sourceElement.scrollLeft / sourceHorizontalMax : 0;

  state.isSyncScrolling = true;
  for (const targetElement of syncedElements) {
    if (targetElement.dataset.compareId === sourceId) {
      continue;
    }
    const targetVerticalMax = targetElement.scrollHeight - targetElement.clientHeight;
    const targetHorizontalMax = targetElement.scrollWidth - targetElement.clientWidth;
    targetElement.scrollTop = targetVerticalMax > 0 ? verticalRatio * targetVerticalMax : 0;
    targetElement.scrollLeft = targetHorizontalMax > 0 ? horizontalRatio * targetHorizontalMax : 0;
  }
  state.isSyncScrolling = false;
}

function formatMiddleTruncatedPath(path, maxLength) {
  if (path.length <= maxLength) {
    return path;
  }

  const segments = path.split("/");
  if (segments.length <= 4) {
    return `${path.slice(0, maxLength - 1)}…`;
  }

  const head = segments.slice(0, 2).join("/");
  const tail = segments.slice(-2).join("/");
  const candidate = `${head}/…/${tail}`;
  if (candidate.length <= maxLength) {
    return candidate;
  }

  return `${head}/…/${segments.at(-1) || ""}`;
}

function compareStatusLabel(variant) {
  if (!variant.exists) {
    return "missing";
  }
  if (variant.kind === "source") {
    return "canonical";
  }
  return variant.matches_source ? "matches source" : "differs";
}

function buildCompareBadge(text, tone) {
  const badge = document.createElement("span");
  badge.className = `sync-compare-badge sync-compare-badge--${tone}`;
  badge.textContent = text;
  return badge;
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
  setEditorReadOnlyMode(false);
  dom.editorPath.textContent = relativePath;
  dom.editorPath.title = relativePath;
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
    markSyncPlanStale();
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
  if (state.syncRequestInFlight) {
    return;
  }

  setSyncButtonsBusy(true, "build");
  setStatus("Building sync plan...");
  try {
    const plan = await fetchSyncPlan(false);
    renderSyncPlan(plan);
    setStatus("Sync plan ready.");
  } catch (error) {
    setStatus(`Sync plan failed: ${error.message}`);
  } finally {
    setSyncButtonsBusy(false);
  }
}

async function applySyncPlan() {
  if (state.syncRequestInFlight) {
    return;
  }

  if (!window.confirm("Apply create/update sync actions? Delete candidates are not removed.")) {
    return;
  }

  setSyncButtonsBusy(true, "apply");
  setStatus("Applying sync plan...");
  try {
    const result = await fetchJson("/api/sync-apply", {
      method: "POST",
      body: JSON.stringify({ confirm: true }),
    });
    const plan = await fetchSyncPlan(false);
    renderSyncPlan(plan);
    setStatus(
      `Sync apply complete: created=${result.created} updated=${result.updated} skipped=${result.skipped}`
    );
  } catch (error) {
    markSyncPlanStale();
    setStatus(`Sync apply failed: ${error.message}`);
  } finally {
    setSyncButtonsBusy(false);
  }
}

async function init() {
  wireThemeToggle();
  setSyncButtonsBusy(false);
  updateSyncPlanStateLine();
  if (dom.syncDiffBackdrop) {
    dom.syncDiffBackdrop.addEventListener("click", closeSyncDiffModal);
  }
  if (dom.syncDiffClose) {
    dom.syncDiffClose.addEventListener("click", closeSyncDiffModal);
  }
  if (dom.syncDiffCloseX) {
    dom.syncDiffCloseX.addEventListener("click", closeSyncDiffModal);
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeSyncDiffModal();
    }
  });
  if (dom.syncCompareCopyPath) {
    dom.syncCompareCopyPath.addEventListener("click", async () => {
      if (!state.currentComparePath) {
        return;
      }
      try {
        await navigator.clipboard.writeText(state.currentComparePath);
        setStatus("Compare path copied.");
      } catch {
        setStatus("Unable to copy compare path.");
      }
    });
  }

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
