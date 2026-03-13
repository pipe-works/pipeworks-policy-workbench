import {
  SYNC_ACTION_SORT_ORDER,
  SYNC_APPLY_LABEL,
  SYNC_REFRESH_LABEL,
} from "./constants.js";
import { dom } from "./dom.js";
import { state } from "./state.js";
import { openSyncAction, showSyncCompare } from "./sync_compare.js";

let _fetchJson = null;
let _setStatus = null;
let _formatLocalDateTime = null;

export function configureSyncPlan({
  fetchJson,
  setStatus,
  formatLocalDateTime,
}) {
  _fetchJson = fetchJson;
  _setStatus = setStatus;
  _formatLocalDateTime = formatLocalDateTime;
}

function requireSyncPlanDeps() {
  if (!_fetchJson || !_setStatus || !_formatLocalDateTime) {
    throw new Error("Sync plan helpers are not configured.");
  }
}

function updateSyncPlanStateLine() {
  if (!dom.syncPlanState) {
    return;
  }

  if (!state.syncPlanBuiltAt) {
    dom.syncPlanState.textContent = "not generated yet";
    return;
  }

  const builtText = _formatLocalDateTime(state.syncPlanBuiltAt);
  if (state.syncPlanIsStale) {
    dom.syncPlanState.textContent = `stale | last generated ${builtText}`;
    return;
  }

  dom.syncPlanState.textContent = `fresh | generated ${builtText}`;
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

async function fetchSyncPlan(includeUnchanged = false) {
  return _fetchJson(`/api/sync-plan?include_unchanged=${includeUnchanged}`);
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

export function updateReviewedStateLine() {
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

function buildSyncSummaryPill(text, tone) {
  const chip = document.createElement("span");
  chip.className = `sync-summary-chip sync-summary-chip--${tone}`;
  chip.textContent = text;
  return chip;
}

function renderSyncSummaryChips(visibleCounts) {
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

export function renderUnchangedBreakdown(plan) {
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

  renderSyncSummaryChips(visibleCounts);
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

export function markSyncPlanStale() {
  state.syncPlanIsStale = true;
  updateSyncPlanStateLine();
  updateSyncButtonsAvailability();
  updateSyncApplyHint();
}

export async function buildSyncPlan() {
  requireSyncPlanDeps();
  if (state.syncRequestInFlight) {
    return;
  }

  setSyncButtonsBusy(true, "build");
  _setStatus("Building sync plan...");
  try {
    const plan = await fetchSyncPlan(false);
    renderSyncPlan(plan);
    _setStatus("Sync plan ready.");
  } catch (error) {
    markSyncPlanStale();
    _setStatus(`Sync plan failed: ${error.message}`);
  } finally {
    setSyncButtonsBusy(false);
  }
}

export async function applySyncPlan() {
  requireSyncPlanDeps();
  if (state.syncRequestInFlight) {
    return;
  }

  if (!window.confirm("Apply create/update sync actions? Target-only files are not removed.")) {
    return;
  }

  setSyncButtonsBusy(true, "apply");
  _setStatus("Applying sync plan...");
  try {
    const result = await _fetchJson("/api/sync-apply", {
      method: "POST",
      body: JSON.stringify({ confirm: true }),
    });
    const plan = await fetchSyncPlan(false);
    renderSyncPlan(plan);
    _setStatus(
      `Sync apply complete: created=${result.created} updated=${result.updated} skipped=${result.skipped}`
    );
  } catch (error) {
    markSyncPlanStale();
    _setStatus(`Sync apply failed: ${error.message}`);
  } finally {
    setSyncButtonsBusy(false);
  }
}

export function initializeSyncPlanUi() {
  requireSyncPlanDeps();
  setSyncButtonsBusy(false);
  updateSyncPlanStateLine();
  updateReviewedStateLine();
}
