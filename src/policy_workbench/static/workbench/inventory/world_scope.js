import { dom } from "../dom.js";
import { state } from "../state.js";
import { setServerFeatureAvailability } from "../runtime.js";

function normalizeWorldRows(worldRows) {
  const normalizedRows = [];
  const seenIds = new Set();
  for (const row of worldRows || []) {
    if (!row || typeof row !== "object") {
      continue;
    }
    const worldId = String(row.id || "").trim();
    if (!worldId || seenIds.has(worldId)) {
      continue;
    }
    seenIds.add(worldId);
    normalizedRows.push({
      ...row,
      id: worldId,
      name: String(row.name || "").trim(),
      can_access: row.can_access !== false,
      is_active: row.is_active !== false,
    });
  }
  return normalizedRows;
}

function choosePreferredWorldId(worldRows, preferredWorldId, previousWorldId) {
  const availableIds = new Set((worldRows || []).map((row) => row.id));
  const preferred = String(preferredWorldId || "").trim();
  if (preferred && availableIds.has(preferred)) {
    return preferred;
  }
  const previous = String(previousWorldId || "").trim();
  if (previous && availableIds.has(previous)) {
    return previous;
  }

  const defaultWorld = (worldRows || []).find((row) => row.is_active && row.can_access);
  if (defaultWorld) {
    return defaultWorld.id;
  }
  return String(worldRows?.[0]?.id || "").trim();
}

function buildWorldLabel(worldRow) {
  const worldId = String(worldRow.id || "").trim();
  const worldName = String(worldRow.name || "").trim();
  const label = worldName || worldId;

  const suffixes = [];
  if (!worldRow.is_active) {
    suffixes.push("inactive");
  }
  if (!worldRow.can_access) {
    suffixes.push("locked");
  }
  if (suffixes.length) {
    return `${label} [${suffixes.join(", ")}]`;
  }
  return label;
}

export function setAvailableWorldOptions(worldRows, { preferredWorldId = "" } = {}) {
  const normalizedRows = normalizeWorldRows(worldRows);
  state.availableWorlds = normalizedRows;
  if (!dom.inventoryWorld) {
    state.selectedWorldId = choosePreferredWorldId(
      normalizedRows,
      preferredWorldId,
      state.selectedWorldId
    );
    return;
  }

  const previouslySelected = String(dom.inventoryWorld.value || "").trim();
  const nextWorldId = choosePreferredWorldId(normalizedRows, preferredWorldId, previouslySelected);
  dom.inventoryWorld.innerHTML = "";

  if (!normalizedRows.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No worlds available";
    dom.inventoryWorld.appendChild(option);
    dom.inventoryWorld.value = "";
    state.selectedWorldId = "";
    updateActivationScopeLabel();
    setServerFeatureAvailability();
    return;
  }

  for (const worldRow of normalizedRows) {
    const option = document.createElement("option");
    option.value = worldRow.id;
    option.textContent = buildWorldLabel(worldRow);
    dom.inventoryWorld.appendChild(option);
  }
  if (nextWorldId) {
    dom.inventoryWorld.value = nextWorldId;
  }

  state.selectedWorldId = String(dom.inventoryWorld.value || "").trim();
  updateActivationScopeLabel();
  setServerFeatureAvailability();
}

export function clearAvailableWorldOptions() {
  setAvailableWorldOptions([], { preferredWorldId: "" });
}

export function readActivationScopeInputs() {
  const worldId = (dom.inventoryWorld?.value || state.selectedWorldId || "").trim();
  const clientProfile = (dom.activationClientProfile?.value || "").trim();
  state.selectedWorldId = worldId;
  return {
    worldId,
    clientProfile,
    scope: clientProfile ? `${worldId}:${clientProfile}` : worldId,
  };
}

function updateActivationWorldDisplay() {
  if (!dom.activationWorldDisplay) {
    return;
  }
  const worldId = String(dom.inventoryWorld?.value || state.selectedWorldId || "").trim();
  dom.activationWorldDisplay.textContent = worldId
    ? `World: ${worldId}`
    : "World: none selected";
}

export function updateActivationScopeLabel() {
  updateActivationWorldDisplay();
  if (!dom.activationScopeLabel) {
    updateActivationSaveSummary();
    return;
  }
  const { worldId, clientProfile } = readActivationScopeInputs();
  if (!worldId) {
    dom.activationScopeLabel.textContent = "Scope: none selected";
    updateActivationSaveSummary();
    return;
  }
  dom.activationScopeLabel.textContent = clientProfile
    ? `Scope: ${worldId}:${clientProfile}`
    : `Scope: ${worldId}`;
  updateActivationSaveSummary();
}

export function updateActivationSaveSummary() {
  if (!dom.activationSaveSummary) {
    return;
  }
  const saveScopeMode = String(dom.saveScopeMode?.value || "world_only").trim();
  const isWorldOnlyMode = saveScopeMode !== "global_update";
  const rolloutAllWorlds = Boolean(dom.saveRolloutAllWorlds?.checked);
  if (dom.activationEnable) {
    if (isWorldOnlyMode) {
      dom.activationEnable.checked = true;
    }
  }
  if (dom.saveRolloutAllWorldsRow) {
    dom.saveRolloutAllWorldsRow.hidden = !isWorldOnlyMode;
  }
  if (dom.activationEnableRow) {
    dom.activationEnableRow.hidden = isWorldOnlyMode;
  }
  const activateAfterSave = isWorldOnlyMode ? true : Boolean(dom.activationEnable?.checked);
  const { worldId, scope } = readActivationScopeInputs();
  const summaryLabel = dom.activationSaveSummary;
  summaryLabel.classList.remove("activation-save-summary__meta--warning");

  if (isWorldOnlyMode) {
    if (!worldId) {
      summaryLabel.textContent = "Will save only for the current world. Choose a world first.";
      summaryLabel.classList.add("activation-save-summary__meta--warning");
      setServerFeatureAvailability();
      return;
    }
    summaryLabel.textContent = rolloutAllWorlds
      ? `Will save for ${scope}, then apply the same variant to all accessible worlds.`
      : `Will save for ${scope} only. Other worlds stay unchanged.`;
    setServerFeatureAvailability();
    return;
  }

  if (!activateAfterSave) {
    summaryLabel.textContent = "Will update the shared variant only. No activation change.";
    setServerFeatureAvailability();
    return;
  }

  if (!worldId) {
    summaryLabel.textContent = "Will update shared variant and activate it after save. Choose a world first.";
    summaryLabel.classList.add("activation-save-summary__meta--warning");
    setServerFeatureAvailability();
    return;
  }

  summaryLabel.textContent = `Will update shared variant and activate it for ${scope}.`;
  setServerFeatureAvailability();
}
