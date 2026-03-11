const dom = {
  workbenchGrid: document.getElementById("workbench-grid"),
  panelTree: document.getElementById("panel-tree"),
  treeSummaryDirectories: document.getElementById("tree-summary-directories"),
  treeSummaryFiles: document.getElementById("tree-summary-files"),
  treeList: document.getElementById("tree-list"),
  editorPath: document.getElementById("editor-path"),
  fileEditor: document.getElementById("file-editor"),
  inventoryPolicyType: document.getElementById("inventory-policy-type"),
  inventoryNamespace: document.getElementById("inventory-namespace"),
  inventoryStatus: document.getElementById("inventory-status"),
  inventoryCount: document.getElementById("inventory-count"),
  inventoryList: document.getElementById("inventory-list"),
  btnToggleTree: document.getElementById("btn-toggle-tree"),
  btnExpandTree: document.getElementById("btn-expand-tree"),
  themeToggle: document.getElementById("theme-toggle"),
  validationCounts: document.getElementById("validation-counts"),
  validationList: document.getElementById("validation-list"),
  hashStatusOverall: document.getElementById("hash-status-overall"),
  hashStateTableBody: document.getElementById("hash-state-table-body"),
  hashCanonicalRoot: document.getElementById("hash-canonical-root"),
  hashCanonicalUrl: document.getElementById("hash-canonical-url"),
  hashCanonicalError: document.getElementById("hash-canonical-error"),
  hashGeneratedAt: document.getElementById("hash-generated-at"),
  hashFileCount: document.getElementById("hash-file-count"),
  hashFileCountRow: document.getElementById("hash-file-count-row"),
  hashTargets: document.getElementById("hash-targets"),
  syncCounts: document.getElementById("sync-counts"),
  syncPlanState: document.getElementById("sync-plan-state"),
  syncReviewedState: document.getElementById("sync-reviewed-state"),
  syncApplyHint: document.getElementById("sync-apply-hint"),
  syncList: document.getElementById("sync-list"),
  syncUnchangedBody: document.getElementById("sync-unchanged-body"),
  syncUnchangedTotal: document.getElementById("sync-unchanged-total"),
  syncTabs: Array.from(document.querySelectorAll("[data-sync-tab]")),
  syncPanels: Array.from(document.querySelectorAll(".sync-step[data-sync-step]")),
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
  btnRefreshInventory: document.getElementById("btn-refresh-inventory"),
  btnRefreshHash: document.getElementById("btn-refresh-hash"),
  btnCopyHash: document.getElementById("btn-copy-hash"),
  btnSaveFile: document.getElementById("btn-save-file"),
  btnReloadFile: document.getElementById("btn-reload-file"),
  btnRunValidation: document.getElementById("btn-run-validation"),
  btnBuildSync: document.getElementById("btn-build-sync"),
  btnApplySync: document.getElementById("btn-apply-sync"),
};

const state = {
  selectedPath: "",
  selectedArtifact: null,
  selectedPolicyRecord: null,
  fileIndex: [],
  inventoryItems: [],
  sourceRoot: "",
  directoriesCount: 0,
  currentComparePath: "",
  currentCompareRelativePath: "",
  hashStatus: null,
  hashRequestInFlight: false,
  syncPlanBuiltAt: null,
  syncPlanIsStale: true,
  syncRequestInFlight: false,
  syncBusyMode: "",
  currentPlanHasActionable: false,
  reviewedActionKeys: new Set(),
  currentPlanActionCount: 0,
  latestSyncPlan: null,
  hashCopyFeedbackTimer: null,
  compareContentElements: [],
  syncedCompareIds: new Set(),
  isSyncScrolling: false,
  treeCollapsed: false,
  activeSyncStep: "build",
};

const THEME_STORAGE_KEY = "ppw-theme";
const HASH_REFRESH_LABEL = "Refresh Hash Snapshot";
const SYNC_REFRESH_LABEL = "Refresh Dry-Run Plan";
const SYNC_APPLY_LABEL = "Apply Create/Update";
const SYNC_STEP_KEYS = new Set(["build", "review", "apply"]);
const SYNC_ACTION_SORT_ORDER = {
  update: 0,
  create: 1,
  target_only: 2,
  unchanged: 3,
};

function setStatus(message) {
  dom.statusText.textContent = message;
}

function setEditorReadOnlyMode(isReadOnly) {
  dom.fileEditor.readOnly = isReadOnly;
  dom.fileEditor.classList.toggle("is-readonly", isReadOnly);
  dom.btnSaveFile.disabled = isReadOnly;
  dom.btnReloadFile.disabled = isReadOnly;
}

function setTreeCollapsed(isCollapsed) {
  state.treeCollapsed = Boolean(isCollapsed);
  if (dom.workbenchGrid) {
    dom.workbenchGrid.classList.toggle("is-tree-collapsed", state.treeCollapsed);
  }

  if (dom.btnToggleTree) {
    dom.btnToggleTree.textContent = state.treeCollapsed ? "▶" : "◀";
    dom.btnToggleTree.setAttribute("aria-expanded", state.treeCollapsed ? "false" : "true");
    dom.btnToggleTree.setAttribute(
      "aria-label",
      state.treeCollapsed ? "Expand Policy Tree panel" : "Collapse Policy Tree panel"
    );
    dom.btnToggleTree.title = state.treeCollapsed
      ? "Expand Policy Tree panel"
      : "Collapse Policy Tree panel";
  }

  if (dom.btnExpandTree) {
    dom.btnExpandTree.hidden = !state.treeCollapsed;
  }
}

function setActiveSyncStep(stepKey) {
  const normalized = SYNC_STEP_KEYS.has(stepKey) ? stepKey : "build";
  state.activeSyncStep = normalized;

  for (const tab of dom.syncTabs) {
    const isActive = tab.dataset.syncTab === normalized;
    tab.classList.toggle("is-active", isActive);
    tab.setAttribute("aria-selected", isActive ? "true" : "false");
    tab.tabIndex = isActive ? 0 : -1;
  }

  for (const panel of dom.syncPanels) {
    panel.hidden = panel.dataset.syncStep !== normalized;
  }
}

function wireSyncTabs() {
  for (const tab of dom.syncTabs) {
    tab.addEventListener("click", () => {
      const tabKey = tab.dataset.syncTab || "build";
      setActiveSyncStep(tabKey);
    });
  }
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
    dom.syncPlanState.textContent = "not generated yet";
    return;
  }

  const builtText = formatLocalDateTime(state.syncPlanBuiltAt);
  if (state.syncPlanIsStale) {
    dom.syncPlanState.textContent = `stale | last generated ${builtText}`;
    return;
  }

  dom.syncPlanState.textContent = `fresh | generated ${builtText}`;
}

function markSyncPlanStale() {
  state.syncPlanIsStale = true;
  updateSyncPlanStateLine();
  updateSyncButtonsAvailability();
  updateSyncApplyHint();
}

function setSyncButtonsBusy(isBusy, mode = "") {
  state.syncRequestInFlight = isBusy;
  state.syncBusyMode = isBusy ? mode : "";

  if (!dom.btnBuildSync || !dom.btnApplySync) {
    return;
  }

  dom.btnBuildSync.disabled = isBusy;
  dom.btnApplySync.disabled = isBusy;
  dom.btnBuildSync.textContent = isBusy && mode === "build" ? "Refreshing..." : SYNC_REFRESH_LABEL;
  dom.btnApplySync.textContent = isBusy && mode === "apply" ? "Applying..." : SYNC_APPLY_LABEL;
  dom.btnBuildSync.setAttribute("aria-busy", isBusy && mode === "build" ? "true" : "false");
  dom.btnApplySync.setAttribute("aria-busy", isBusy && mode === "apply" ? "true" : "false");

  if (!isBusy) {
    updateSyncButtonsAvailability();
  }
  updateSyncApplyHint();
}

function updateSyncButtonsAvailability() {
  if (!dom.btnBuildSync || !dom.btnApplySync || state.syncRequestInFlight) {
    return;
  }

  dom.btnBuildSync.disabled = false;
  const canApply = Boolean(
    state.syncPlanBuiltAt && !state.syncPlanIsStale && state.currentPlanHasActionable
  );
  dom.btnApplySync.disabled = !canApply;
}

function updateSyncApplyHint() {
  if (!dom.syncApplyHint) {
    return;
  }

  if (state.syncRequestInFlight) {
    dom.syncApplyHint.textContent = state.syncBusyMode === "apply"
      ? "Applying create/update actions..."
      : "Refreshing dry-run plan...";
    return;
  }

  if (!state.syncPlanBuiltAt) {
    dom.syncApplyHint.textContent =
      "Generate a dry-run plan first. Dry-run previews actions and writes nothing.";
    return;
  }

  if (state.syncPlanIsStale) {
    dom.syncApplyHint.textContent = "Plan is stale after edits. Refresh dry-run plan before apply.";
    return;
  }

  if (!state.currentPlanHasActionable) {
    dom.syncApplyHint.textContent =
      "No create/update actions to apply. Target-only files are informational only and never auto-deleted.";
    return;
  }

  dom.syncApplyHint.textContent = "Ready to apply create/update actions.";
}

function setHashButtonBusy(isBusy) {
  state.hashRequestInFlight = isBusy;
  if (!dom.btnRefreshHash) {
    return;
  }

  dom.btnRefreshHash.disabled = isBusy;
  dom.btnRefreshHash.textContent = isBusy ? "Refreshing..." : HASH_REFRESH_LABEL;
  dom.btnRefreshHash.setAttribute("aria-busy", isBusy ? "true" : "false");
}

function formatHashShort(hashText) {
  if (!hashText) {
    return "--";
  }
  if (hashText.length <= 16) {
    return hashText;
  }
  return `${hashText.slice(0, 8)}…${hashText.slice(-6)}`;
}

function formatCanonicalGeneratedAt(rawValue) {
  if (!rawValue) {
    return "--";
  }

  const parsed = new Date(rawValue);
  if (Number.isNaN(parsed.valueOf())) {
    return rawValue;
  }
  return formatLocalDateTime(parsed);
}

function hashStatusTone(status) {
  if (status === "ok") {
    return "ok";
  }
  if (status === "drift") {
    return "warn";
  }
  return "err";
}

function hashStatusText(status) {
  if (status === "ok") {
    return "Aligned";
  }
  if (status === "drift") {
    return "Drift detected";
  }
  return "Canonical unavailable";
}

function renderHashTargets(targets) {
  if (!dom.hashTargets) {
    return;
  }

  dom.hashTargets.innerHTML = "";
  if (!targets.length) {
    const empty = document.createElement("div");
    empty.className = "hash-target-card";
    empty.textContent = "No mirror targets configured.";
    dom.hashTargets.appendChild(empty);
    return;
  }

  for (const target of targets) {
    const card = document.createElement("article");
    card.className = "hash-target-card";

    const top = document.createElement("div");
    top.className = "hash-target-card__top";
    const name = document.createElement("span");
    name.className = "hash-target-card__name";
    name.textContent = target.name;

    const matchBadge = document.createElement("span");
    const matchTone = target.matches_canonical === null
      ? "muted"
      : (target.matches_canonical ? "ok" : "warn");
    matchBadge.className = `hash-target-badge hash-target-badge--${matchTone}`;
    matchBadge.textContent = target.matches_canonical === null
      ? "unknown"
      : (target.matches_canonical ? "aligned" : "drift");
    top.append(name, matchBadge);

    const meta = document.createElement("div");
    meta.className = "hash-target-card__meta";
    meta.append(
      buildHashMetaLine(`missing ${target.missing_count}`),
      buildHashMetaLine(`different ${target.different_count}`),
      buildHashMetaLine(`target-only ${target.target_only_count}`)
    );

    const rootLine = buildHashMetaLine(`hash ${formatHashShort(target.root_hash)}`);
    rootLine.title = target.root_hash;

    card.append(top, meta, rootLine);
    dom.hashTargets.appendChild(card);
  }
}

function renderHashTargetFileCountRows(targets) {
  if (!dom.hashStateTableBody || !dom.hashFileCountRow) {
    return;
  }

  for (const row of dom.hashStateTableBody.querySelectorAll(".hash-target-file-row")) {
    row.remove();
  }

  let insertAfter = dom.hashFileCountRow;
  for (const target of targets) {
    const row = document.createElement("tr");
    row.className = "hash-target-file-row";

    const labelCell = document.createElement("th");
    labelCell.scope = "row";
    labelCell.textContent = `${target.name} files`;

    const valueCell = document.createElement("td");
    valueCell.textContent = `${target.file_count}`;

    row.append(labelCell, valueCell);
    insertAfter.insertAdjacentElement("afterend", row);
    insertAfter = row;
  }
}

function buildHashMetaLine(text) {
  const line = document.createElement("span");
  line.className = "hash-target-card__line";
  line.textContent = text;
  return line;
}

function renderHashStatus(payload) {
  state.hashStatus = payload;
  if (dom.hashStatusOverall) {
    dom.hashStatusOverall.textContent = hashStatusText(payload.status);
    dom.hashStatusOverall.className = `hash-target-badge hash-target-badge--${hashStatusTone(payload.status)}`;
  }

  if (dom.hashCanonicalRoot) {
    if (payload.canonical) {
      dom.hashCanonicalRoot.textContent = formatHashShort(payload.canonical.root_hash);
      dom.hashCanonicalRoot.title = payload.canonical.root_hash;
    } else {
      dom.hashCanonicalRoot.textContent = "--";
      dom.hashCanonicalRoot.title = "";
    }
  }

  if (dom.hashGeneratedAt) {
    dom.hashGeneratedAt.textContent = payload.canonical
      ? formatCanonicalGeneratedAt(payload.canonical.generated_at)
      : "--";
  }

  if (dom.hashCanonicalUrl) {
    dom.hashCanonicalUrl.textContent = payload.canonical_url || "--";
    dom.hashCanonicalUrl.title = payload.canonical_url || "";
  }

  if (dom.hashCanonicalError) {
    if (payload.canonical_error) {
      dom.hashCanonicalError.textContent = payload.canonical_error;
      dom.hashCanonicalError.className = "hash-detail hash-detail--err";
    } else if (payload.canonical) {
      dom.hashCanonicalError.textContent = "canonical snapshot available";
      dom.hashCanonicalError.className = "hash-detail hash-detail--ok";
    } else {
      dom.hashCanonicalError.textContent = "--";
      dom.hashCanonicalError.className = "hash-detail hash-detail--muted";
    }
  }

  if (dom.hashFileCount) {
    dom.hashFileCount.textContent = payload.canonical ? `${payload.canonical.file_count}` : "--";
  }

  if (dom.btnCopyHash) {
    dom.btnCopyHash.disabled = !payload.canonical;
  }

  const targets = payload.targets || [];
  renderHashTargetFileCountRows(targets);
  renderHashTargets(targets);
  if (state.latestSyncPlan) {
    renderUnchangedBreakdown(state.latestSyncPlan);
  }
}

async function refreshHashStatus() {
  if (state.hashRequestInFlight) {
    return;
  }

  setHashButtonBusy(true);
  setStatus("Refreshing hash snapshot...");
  try {
    const payload = await fetchJson("/api/hash-status");
    renderHashStatus(payload);
    if (payload.status === "ok") {
      setStatus("Hash snapshot aligned.");
    } else if (payload.status === "drift") {
      setStatus("Hash snapshot updated: drift detected.");
    } else {
      setStatus("Hash snapshot updated: canonical endpoint unavailable.");
    }
  } catch (error) {
    setStatus(`Hash snapshot failed: ${error.message}`);
  } finally {
    setHashButtonBusy(false);
  }
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

function buildPolicySelectorLabel(item) {
  return `${item.policy_type}:${item.namespace}:${item.policy_key}:${item.variant}`;
}

function selectedPolicyKey() {
  if (!state.selectedPolicyRecord) {
    return "";
  }
  return `${state.selectedPolicyRecord.policy_id}:${state.selectedPolicyRecord.variant}`;
}

function setEditorFromPolicyRecord(policy) {
  state.selectedPolicyRecord = policy;
  state.selectedPath = "";
  state.selectedArtifact = {
    policy_type: policy.policy_type,
    namespace: policy.namespace,
    policy_key: policy.policy_key,
    variant: policy.variant,
    is_authorable: true,
  };
  setEditorReadOnlyMode(false);
  dom.editorPath.textContent = `${policy.policy_id}:${policy.variant} · api-first`;
  dom.editorPath.title =
    `${policy.policy_id}:${policy.variant}\nstatus=${policy.status} version=${policy.policy_version}`;
  dom.fileEditor.value = buildRawEditorContentFromPolicy(policy);
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
  if (policy.policy_type === "tone_profile") {
    return JSON.stringify(content, null, 2);
  }
  if (policy.policy_type === "descriptor_layer" || policy.policy_type === "registry") {
    return JSON.stringify(content, null, 2);
  }
  return JSON.stringify(content, null, 2);
}

function renderPolicyInventory(items) {
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
    item.textContent = "No policies matched current filters.";
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

async function refreshPolicyInventory() {
  setStatus("Loading API-first policy inventory...");
  try {
    const query = buildPolicyInventoryQueryString();
    const suffix = query ? `?${query}` : "";
    const payload = await fetchJson(`/api/policies${suffix}`);
    renderPolicyInventory(payload.items || []);
    setStatus(`Policy inventory loaded (${payload.item_count || 0} items).`);
  } catch (error) {
    setStatus(`Policy inventory load failed: ${error.message}`);
  }
}

async function loadPolicyObject(policyId, variant = "") {
  setStatus(`Loading policy object ${policyId}:${variant || "latest"}...`);
  try {
    const query = new URLSearchParams();
    if ((variant || "").trim()) {
      query.set("variant", variant.trim());
    }
    const suffix = query.toString() ? `?${query.toString()}` : "";
    const payload = await fetchJson(`/api/policies/${encodeURIComponent(policyId)}${suffix}`);
    setEditorFromPolicyRecord(payload);
    renderPolicyInventory(state.inventoryItems);
    setStatus(`Loaded ${payload.policy_id}:${payload.variant} from mud-server API.`);
  } catch (error) {
    setStatus(`Policy object load failed: ${error.message}`);
  }
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
      button.addEventListener("click", () => loadFile(artifact.relative_path, artifact));

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
  state.latestSyncPlan = plan;
  const visibleCounts = {
    create: 0,
    update: 0,
    unchanged: 0,
    target_only: 0,
  };
  for (const action of plan.actions) {
    if (Object.prototype.hasOwnProperty.call(visibleCounts, action.action)) {
      visibleCounts[action.action] += 1;
    }
  }

  renderSyncSummaryChips(plan, visibleCounts);
  renderUnchangedBreakdown(plan);
  pruneReviewedActionKeys(plan.actions);

  state.syncPlanBuiltAt = new Date();
  state.syncPlanIsStale = false;
  state.currentPlanHasActionable = plan.actions.some(
    (action) => action.action === "create" || action.action === "update"
  );
  updateSyncPlanStateLine();
  updateSyncButtonsAvailability();
  updateSyncApplyHint();
  updateReviewedStateLine();

  dom.syncList.innerHTML = "";
  if (!plan.actions.length) {
    const item = document.createElement("li");
    item.className = "report-item report-item--info";
    item.textContent = "No visible sync actions. This plan is already aligned for create/update paths.";
    dom.syncList.appendChild(item);
    return;
  }

  const groupedByTarget = groupSyncActionsByTarget(plan.actions);
  for (const [targetName, actions] of groupedByTarget) {
    const groupItem = document.createElement("li");
    groupItem.className = "sync-target-group";

    const details = document.createElement("details");
    details.className = "sync-target-group__details";
    details.open = true;

    const summary = document.createElement("summary");
    summary.className = "sync-target-group__summary";

    const title = document.createElement("span");
    title.className = "sync-target-group__title";
    title.textContent = targetName;

    const meta = document.createElement("span");
    meta.className = "sync-target-group__meta";
    const groupCounts = countSyncActions(actions);
    meta.append(
      buildSyncSummaryPill(`actions ${actions.length}`, "muted"),
      buildSyncSummaryPill(`update ${groupCounts.update}`, "info"),
      buildSyncSummaryPill(`create ${groupCounts.create}`, "ok"),
      buildSyncSummaryPill(`target-only ${groupCounts.target_only}`, "err")
    );
    summary.append(title, meta);

    const actionsList = document.createElement("ul");
    actionsList.className = "sync-target-group__list";
    for (const action of actions) {
      actionsList.appendChild(buildSyncActionCard(action));
    }

    details.append(summary, actionsList);
    groupItem.appendChild(details);
    dom.syncList.appendChild(groupItem);
  }
}

function buildSyncActionCard(action) {
  const actionKey = buildSyncActionKey(action);
  const cardItem = document.createElement("li");
  cardItem.className = "sync-impact-action";

  const tone = action.action === "target_only"
    ? "err"
    : (action.action === "create" ? "ok" : "info");
  cardItem.classList.add(`sync-impact-action--${tone}`);

  const top = document.createElement("div");
  top.className = "sync-impact-action__top";
  const badge = document.createElement("span");
  badge.className = `sync-impact-action__badge sync-impact-action__badge--${tone}`;
  badge.textContent = action.action;
  const path = document.createElement("span");
  path.className = "sync-impact-action__path";
  path.textContent = action.relative_path;
  path.title = action.relative_path;
  top.append(badge, path);

  const reason = document.createElement("div");
  reason.className = "sync-impact-action__reason";
  reason.textContent = action.reason || "No additional reason.";

  const controls = document.createElement("div");
  controls.className = "sync-impact-action__controls";

  const reviewLabel = document.createElement("label");
  reviewLabel.className = "sync-impact-action__review";
  const reviewToggle = document.createElement("input");
  reviewToggle.type = "checkbox";
  reviewToggle.checked = state.reviewedActionKeys.has(actionKey);
  const reviewText = document.createElement("span");
  reviewText.textContent = "Reviewed";
  reviewLabel.append(reviewToggle, reviewText);

  reviewToggle.addEventListener("change", () => {
    if (reviewToggle.checked) {
      state.reviewedActionKeys.add(actionKey);
    } else {
      state.reviewedActionKeys.delete(actionKey);
    }
    updateReviewedStateLine();
  });

  const buttonRow = document.createElement("div");
  buttonRow.className = "sync-impact-action__buttons";

  const compareButton = document.createElement("button");
  compareButton.className = "btn btn--secondary btn--sm";
  compareButton.type = "button";
  compareButton.textContent = "Compare";
  compareButton.title = "Compare canonical source and targets for this path";
  compareButton.addEventListener("click", () => showSyncCompare(action));

  const openButton = document.createElement("button");
  openButton.className = "btn btn--secondary btn--sm";
  openButton.type = "button";
  openButton.textContent = action.action === "target_only" ? "Open Target" : "Open Canonical";
  openButton.title = action.action === "target_only"
    ? "Open target snapshot in read-only mode"
    : "Open canonical source file in the editor";
  openButton.addEventListener("click", () => {
    void openSyncAction(action);
  });

  buttonRow.append(compareButton, openButton);
  controls.append(reviewLabel, buttonRow);

  cardItem.append(top, reason, controls);
  return cardItem;
}

function buildSyncActionKey(action) {
  return `${action.target}::${action.action}::${action.relative_path}`;
}

function pruneReviewedActionKeys(actions) {
  const actionKeys = new Set(actions.map((action) => buildSyncActionKey(action)));
  state.reviewedActionKeys = new Set(
    [...state.reviewedActionKeys].filter((actionKey) => actionKeys.has(actionKey))
  );
  state.currentPlanActionCount = actions.length;
}

function updateReviewedStateLine() {
  if (!dom.syncReviewedState) {
    return;
  }

  const reviewedCount = state.reviewedActionKeys.size;
  dom.syncReviewedState.textContent = `${reviewedCount} / ${state.currentPlanActionCount} actions`;
}

function groupSyncActionsByTarget(actions) {
  const grouped = new Map();
  for (const action of actions) {
    if (!grouped.has(action.target)) {
      grouped.set(action.target, []);
    }
    grouped.get(action.target).push(action);
  }

  return [...grouped.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([targetName, groupedActions]) => [
      targetName,
      [...groupedActions].sort((left, right) => {
        const leftRank = SYNC_ACTION_SORT_ORDER[left.action] ?? Number.MAX_SAFE_INTEGER;
        const rightRank = SYNC_ACTION_SORT_ORDER[right.action] ?? Number.MAX_SAFE_INTEGER;
        if (leftRank !== rightRank) {
          return leftRank - rightRank;
        }
        return left.relative_path.localeCompare(right.relative_path);
      }),
    ]);
}

function countSyncActions(actions) {
  const counts = { create: 0, update: 0, unchanged: 0, target_only: 0 };
  for (const action of actions) {
    if (Object.prototype.hasOwnProperty.call(counts, action.action)) {
      counts[action.action] += 1;
    }
  }
  return counts;
}

function renderSyncSummaryChips(plan, visibleCounts) {
  if (!dom.syncCounts) {
    return;
  }

  dom.syncCounts.innerHTML = "";
  dom.syncCounts.append(
    buildSyncSummaryPill(`Updates ${visibleCounts.update}`, "info"),
    buildSyncSummaryPill(`Creates ${visibleCounts.create}`, "ok"),
    buildSyncSummaryPill(`Target-only ${visibleCounts.target_only}`, "err")
  );
}

function renderUnchangedBreakdown(plan) {
  if (!dom.syncUnchangedBody || !dom.syncUnchangedTotal) {
    return;
  }

  dom.syncUnchangedBody.innerHTML = "";

  const canonicalCount = state.hashStatus?.canonical?.file_count;
  const targets = state.hashStatus?.targets || [];
  const totalFromPlan = Number(plan?.counts?.unchanged);

  if (!Number.isInteger(canonicalCount) || !targets.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 3;
    cell.textContent = !Number.isInteger(canonicalCount)
      ? "Refresh Step 1 hash snapshot to populate per-target unchanged arithmetic."
      : "No target directories available.";
    row.appendChild(cell);
    dom.syncUnchangedBody.appendChild(row);
    dom.syncUnchangedTotal.textContent = Number.isInteger(totalFromPlan) ? `${totalFromPlan}` : "--";
    return;
  }

  let derivedTotal = 0;
  const sortedTargets = [...targets].sort((left, right) => left.name.localeCompare(right.name));
  for (const target of sortedTargets) {
    const missing = Number(target.missing_count || 0);
    const different = Number(target.different_count || 0);
    const unchanged = Math.max(0, canonicalCount - missing - different);
    derivedTotal += unchanged;

    const row = document.createElement("tr");

    const targetCell = document.createElement("td");
    targetCell.textContent = target.name;

    const arithmeticCell = document.createElement("td");
    arithmeticCell.textContent = `${canonicalCount} - ${missing} - ${different}`;

    const unchangedCell = document.createElement("td");
    unchangedCell.textContent = `${unchanged}`;

    row.append(targetCell, arithmeticCell, unchangedCell);
    dom.syncUnchangedBody.appendChild(row);
  }

  if (Number.isInteger(totalFromPlan) && totalFromPlan !== derivedTotal) {
    dom.syncUnchangedTotal.textContent = `${totalFromPlan} (calc ${derivedTotal})`;
    return;
  }

  dom.syncUnchangedTotal.textContent = Number.isInteger(totalFromPlan)
    ? `${totalFromPlan}`
    : `${derivedTotal}`;
}

function buildSyncSummaryPill(text, tone) {
  const chip = document.createElement("span");
  chip.className = `sync-summary-chip sync-summary-chip--${tone}`;
  chip.textContent = text;
  return chip;
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
  state.selectedPolicyRecord = null;
  setEditorReadOnlyMode(true);
  dom.editorPath.textContent = `${variant.label} (read-only)`;
  dom.editorPath.title = `${variant.label}: ${displayPath}`;
  dom.fileEditor.value = variant.exists ? variant.content || "" : "<missing file>";
  closeSyncDiffModal();
  setStatus(`Opened ${variant.label} snapshot (${displayPath}) in read-only mode.`);
}

async function openSyncAction(action) {
  if (action.action !== "target_only") {
    await loadFile(action.relative_path);
    return;
  }

  setStatus(`Loading ${action.target} snapshot for ${action.relative_path}...`);
  try {
    const payload = await fetchJson(
      `/api/sync-compare?relative_path=${encodeURIComponent(action.relative_path)}&focus_target=${encodeURIComponent(action.target)}`
    );
    state.currentCompareRelativePath = payload.relative_path;
    state.currentComparePath = `pipeworks_web/policies/${payload.relative_path}`;
    const targetVariant = payload.variants.find((variant) => variant.target === action.target);
    if (!targetVariant) {
      setStatus(`Unable to locate target snapshot for ${action.target}.`);
      return;
    }
    await openCompareVariantInEditor(targetVariant);
  } catch (error) {
    setStatus(`Open action failed: ${error.message}`);
  }
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

function selectedPolicyLabel(artifact) {
  if (!artifact || !artifact.is_authorable) {
    return "read-only";
  }
  return `${artifact.policy_type}:${artifact.namespace}:${artifact.policy_key}:${artifact.variant}`;
}

async function loadFile(relativePath, artifact = null) {
  state.selectedPath = relativePath;
  state.selectedPolicyRecord = null;
  state.selectedArtifact = artifact || state.fileIndex.find(
    (entry) => entry.relative_path === relativePath
  ) || null;
  setEditorReadOnlyMode(false);
  const policyLabel = selectedPolicyLabel(state.selectedArtifact);
  dom.editorPath.textContent = `${relativePath} · ${policyLabel}`;
  dom.editorPath.title = `${relativePath}\n${policyLabel}`;
  setStatus(`Loading ${relativePath}...`);

  try {
    const payload = await fetchJson(
      `/api/file?relative_path=${encodeURIComponent(relativePath)}`
    );
    dom.fileEditor.value = payload.content;
    if (!state.selectedArtifact || !state.selectedArtifact.is_authorable) {
      setEditorReadOnlyMode(true);
      setStatus(`Loaded ${relativePath} in read-only mode (not mapped to policy selector).`);
      return;
    }
    renderTree(state.fileIndex, state.sourceRoot, state.directoriesCount);
    setStatus(`Loaded ${relativePath}.`);
  } catch (error) {
    setStatus(`File load failed: ${error.message}`);
  }
}

async function saveCurrentFile() {
  if (!state.selectedArtifact || !state.selectedArtifact.is_authorable) {
    setStatus("Select an authorable policy object or mapped file before saving.");
    return;
  }

  const targetLabel = state.selectedPath || buildPolicySelectorLabel(state.selectedArtifact);
  setStatus(`Saving ${targetLabel} via mud-server policy API...`);
  try {
    const saveResult = await fetchJson("/api/policy-save", {
      method: "POST",
      body: JSON.stringify({
        policy_type: state.selectedArtifact.policy_type,
        namespace: state.selectedArtifact.namespace,
        policy_key: state.selectedArtifact.policy_key,
        variant: state.selectedArtifact.variant,
        raw_content: dom.fileEditor.value,
        schema_version: "1.0",
        status: "draft",
        activate: false,
      }),
    });
    setStatus(
      `Saved ${saveResult.policy_id}:${saveResult.variant} (v${saveResult.policy_version}).`
    );
    if (state.selectedPolicyRecord) {
      await loadPolicyObject(saveResult.policy_id, saveResult.variant);
    }
    markSyncPlanStale();
  } catch (error) {
    setStatus(`Save failed: ${error.message}`);
  }
}

async function reloadCurrentFile() {
  if (state.selectedPath) {
    await loadFile(state.selectedPath);
    return;
  }
  if (state.selectedPolicyRecord) {
    await loadPolicyObject(state.selectedPolicyRecord.policy_id, state.selectedPolicyRecord.variant);
    return;
  }
  setStatus("Select a file or policy object before reloading.");
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
    markSyncPlanStale();
    setStatus(`Sync plan failed: ${error.message}`);
  } finally {
    setSyncButtonsBusy(false);
  }
}

async function applySyncPlan() {
  if (state.syncRequestInFlight) {
    return;
  }

  if (!window.confirm("Apply create/update sync actions? Target-only files are not removed.")) {
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
  wireSyncTabs();
  setActiveSyncStep("build");
  setTreeCollapsed(false);
  setHashButtonBusy(false);
  if (dom.btnCopyHash) {
    dom.btnCopyHash.disabled = true;
  }
  setSyncButtonsBusy(false);
  updateSyncPlanStateLine();
  updateReviewedStateLine();
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

  if (dom.btnToggleTree) {
    dom.btnToggleTree.addEventListener("click", () => {
      setTreeCollapsed(!state.treeCollapsed);
    });
  }
  if (dom.btnExpandTree) {
    dom.btnExpandTree.addEventListener("click", () => {
      setTreeCollapsed(false);
    });
  }

  dom.btnRefreshTree.addEventListener("click", loadTree);
  if (dom.btnRefreshInventory) {
    dom.btnRefreshInventory.addEventListener("click", refreshPolicyInventory);
  }
  if (dom.inventoryPolicyType) {
    dom.inventoryPolicyType.addEventListener("change", () => {
      void refreshPolicyInventory();
    });
  }
  if (dom.inventoryNamespace) {
    dom.inventoryNamespace.addEventListener("change", () => {
      void refreshPolicyInventory();
    });
  }
  if (dom.inventoryStatus) {
    dom.inventoryStatus.addEventListener("change", () => {
      void refreshPolicyInventory();
    });
  }
  if (dom.btnRefreshHash) {
    dom.btnRefreshHash.addEventListener("click", refreshHashStatus);
  }
  if (dom.btnCopyHash) {
    dom.btnCopyHash.addEventListener("click", async () => {
      const canonicalHash = state.hashStatus?.canonical?.root_hash;
      if (!canonicalHash) {
        setStatus("No canonical hash available to copy.");
        return;
      }

      try {
        await navigator.clipboard.writeText(canonicalHash);
        dom.btnCopyHash.textContent = "Copied";
        dom.btnCopyHash.classList.add("is-copied");
        if (state.hashCopyFeedbackTimer) {
          clearTimeout(state.hashCopyFeedbackTimer);
        }
        state.hashCopyFeedbackTimer = setTimeout(() => {
          dom.btnCopyHash.textContent = "Copy";
          dom.btnCopyHash.classList.remove("is-copied");
          state.hashCopyFeedbackTimer = null;
        }, 1200);
        setStatus("Canonical hash copied.");
      } catch {
        dom.btnCopyHash.textContent = "Retry";
        if (state.hashCopyFeedbackTimer) {
          clearTimeout(state.hashCopyFeedbackTimer);
        }
        state.hashCopyFeedbackTimer = setTimeout(() => {
          dom.btnCopyHash.textContent = "Copy";
          state.hashCopyFeedbackTimer = null;
        }, 1200);
        setStatus("Unable to copy canonical hash.");
      }
    });
  }
  dom.btnSaveFile.addEventListener("click", saveCurrentFile);
  dom.btnReloadFile.addEventListener("click", reloadCurrentFile);
  dom.btnRunValidation.addEventListener("click", runValidation);
  dom.btnBuildSync.addEventListener("click", buildSyncPlan);
  dom.btnApplySync.addEventListener("click", applySyncPlan);

  await refreshHashStatus();
  await refreshPolicyInventory();
  await loadTree();
  await runValidation();
  await buildSyncPlan();
}

init();
