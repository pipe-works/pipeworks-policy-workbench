import { dom } from "./dom.js";
import { state } from "./state.js";
import { setEditorReadOnlyMode } from "./inventory.js";
import { loadFile } from "./tree.js";

let _fetchJson = null;
let _setStatus = null;

export function configureSyncCompare({ fetchJson, setStatus }) {
  _fetchJson = fetchJson;
  _setStatus = setStatus;
}

function requireSyncCompareDeps() {
  if (!_fetchJson || !_setStatus) {
    throw new Error("Sync compare helpers are not configured.");
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
    _setStatus("Cannot open compare variant because no path is loaded.");
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
  _setStatus(`Opened ${variant.label} snapshot (${displayPath}) in read-only mode.`);
}

export async function openSyncAction(action) {
  requireSyncCompareDeps();
  if (action.action !== "target_only") {
    await loadFile(action.relative_path);
    return;
  }

  _setStatus(`Loading ${action.target} snapshot for ${action.relative_path}...`);
  try {
    const payload = await _fetchJson(
      `/api/sync-compare?relative_path=${encodeURIComponent(action.relative_path)}&focus_target=${encodeURIComponent(action.target)}`
    );
    state.currentCompareRelativePath = payload.relative_path;
    state.currentComparePath = `pipeworks_web/policies/${payload.relative_path}`;
    const targetVariant = payload.variants.find((variant) => variant.target === action.target);
    if (!targetVariant) {
      _setStatus(`Unable to locate target snapshot for ${action.target}.`);
      return;
    }
    await openCompareVariantInEditor(targetVariant);
  } catch (error) {
    _setStatus(`Open action failed: ${error.message}`);
  }
}

export function closeSyncDiffModal() {
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

export async function showSyncCompare(action) {
  requireSyncCompareDeps();
  if (!dom.syncDiffTitle || !dom.syncDiffMeta || !dom.syncCompareColumns || !dom.syncComparePath) {
    _setStatus("Diff modal is unavailable in the current page template.");
    return;
  }

  _setStatus(`Loading compare view for ${action.relative_path}...`);

  try {
    const payload = await _fetchJson(
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
    _setStatus(`Compare view loaded for ${action.relative_path}.`);
  } catch (error) {
    _setStatus(`Compare load failed: ${error.message}`);
  }
}
