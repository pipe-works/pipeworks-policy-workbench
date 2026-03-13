import { dom } from "./dom.js";
import { state } from "./state.js";
import {
  setServerFeatureAvailability,
  setSourceBadges,
  updateStatusSourceLine,
} from "./runtime.js";
import { setEditorReadOnlyMode } from "./inventory.js";

let _fetchJson = null;
let _setStatus = null;

export function configureTree({ fetchJson, setStatus }) {
  _fetchJson = fetchJson;
  _setStatus = setStatus;
}

function requireTreeDeps() {
  if (!_fetchJson || !_setStatus) {
    throw new Error("Tree helpers are not configured.");
  }
}

export function setTreeCollapsed(isCollapsed) {
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

function selectedPolicyLabel(artifact) {
  if (!artifact || !artifact.is_authorable) {
    return "read-only";
  }
  return `${artifact.policy_type}:${artifact.namespace}:${artifact.policy_key}:${artifact.variant}`;
}

function renderTree(artifacts, sourceRoot, directoriesCount) {
  state.fileIndex = artifacts;
  state.sourceRoot = sourceRoot;
  state.directoriesCount = directoriesCount;
  if (dom.treeSummaryDirectories) {
    dom.treeSummaryDirectories.textContent = `${directoriesCount}`;
  }
  if (dom.treeSummaryFiles) {
    dom.treeSummaryFiles.textContent = `${artifacts.length}`;
  }
  updateStatusSourceLine();
  setSourceBadges();

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
    details.open = directoryArtifacts.some(
      (artifact) => artifact.relative_path === state.selectedPath
    );

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

      button.append(pathSpan);
      button.addEventListener("click", () => {
        void loadFile(artifact.relative_path, artifact);
      });

      fileItem.appendChild(button);
      filesList.appendChild(fileItem);
    }

    details.append(summary, filesList);
    groupItem.appendChild(details);
    dom.treeList.appendChild(groupItem);
  }
}

export async function loadTree() {
  requireTreeDeps();
  _setStatus("Loading policy tree...");
  try {
    const payload = await _fetchJson("/api/tree");
    renderTree(payload.artifacts, payload.source_root, payload.directories.length);
    _setStatus("Policy tree loaded.");
  } catch (error) {
    _setStatus(`Tree load failed: ${error.message}`);
  }
}

export async function loadFile(relativePath, artifact = null) {
  requireTreeDeps();
  state.selectedPath = relativePath;
  state.selectedPolicyRecord = null;
  state.selectedArtifact = artifact || state.fileIndex.find(
    (entry) => entry.relative_path === relativePath
  ) || null;
  setEditorReadOnlyMode(false);
  const policyLabel = selectedPolicyLabel(state.selectedArtifact);
  dom.editorPath.textContent = `${relativePath} · ${policyLabel}`;
  dom.editorPath.title = `${relativePath}\n${policyLabel}`;
  setSourceBadges();
  setServerFeatureAvailability();
  _setStatus(`Loading ${relativePath}...`);

  try {
    const payload = await _fetchJson(
      `/api/file?relative_path=${encodeURIComponent(relativePath)}`
    );
    dom.fileEditor.value = payload.content;
    if (!state.selectedArtifact || !state.selectedArtifact.is_authorable) {
      setEditorReadOnlyMode(true);
      setSourceBadges();
      _setStatus(`Loaded ${relativePath} in read-only mode (not mapped to policy selector).`);
      return;
    }
    renderTree(state.fileIndex, state.sourceRoot, state.directoriesCount);
    setSourceBadges();
    _setStatus(`Loaded ${relativePath}.`);
  } catch (error) {
    _setStatus(`File load failed: ${error.message}`);
  }
}
