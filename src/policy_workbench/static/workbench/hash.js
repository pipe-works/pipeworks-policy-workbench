import { HASH_REFRESH_LABEL } from "./constants.js";
import { dom } from "./dom.js";
import { state } from "./state.js";

let _fetchJson = null;
let _setStatus = null;
let _formatLocalDateTime = null;
let _renderUnchangedBreakdown = null;

export function configureHash({
  fetchJson,
  setStatus,
  formatLocalDateTime,
  renderUnchangedBreakdown,
}) {
  _fetchJson = fetchJson;
  _setStatus = setStatus;
  _formatLocalDateTime = formatLocalDateTime;
  _renderUnchangedBreakdown = renderUnchangedBreakdown;
}

function requireHashDeps() {
  if (!_fetchJson || !_setStatus || !_formatLocalDateTime || !_renderUnchangedBreakdown) {
    throw new Error("Hash helpers are not configured.");
  }
}

export function setHashButtonBusy(isBusy) {
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
  return _formatLocalDateTime(parsed);
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

function buildHashMetaLine(text) {
  const line = document.createElement("span");
  line.className = "hash-target-card__line";
  line.textContent = text;
  return line;
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
    _renderUnchangedBreakdown(state.latestSyncPlan);
  }
}

export async function refreshHashStatus() {
  requireHashDeps();
  if (state.hashRequestInFlight) {
    return;
  }

  setHashButtonBusy(true);
  _setStatus("Refreshing hash snapshot...");
  try {
    const payload = await _fetchJson("/api/hash-status");
    renderHashStatus(payload);
    if (payload.status === "ok") {
      _setStatus("Hash snapshot aligned.");
    } else if (payload.status === "drift") {
      _setStatus("Hash snapshot updated: drift detected.");
    } else {
      _setStatus("Hash snapshot updated: canonical endpoint unavailable.");
    }
  } catch (error) {
    _setStatus(`Hash snapshot failed: ${error.message}`);
  } finally {
    setHashButtonBusy(false);
  }
}

export async function handleCopyCanonicalHash() {
  requireHashDeps();
  const canonicalHash = state.hashStatus?.canonical?.root_hash;
  if (!canonicalHash) {
    _setStatus("No canonical hash available to copy.");
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
    _setStatus("Canonical hash copied.");
  } catch {
    dom.btnCopyHash.textContent = "Retry";
    if (state.hashCopyFeedbackTimer) {
      clearTimeout(state.hashCopyFeedbackTimer);
    }
    state.hashCopyFeedbackTimer = setTimeout(() => {
      dom.btnCopyHash.textContent = "Copy";
      state.hashCopyFeedbackTimer = null;
    }, 1200);
    _setStatus("Unable to copy canonical hash.");
  }
}

export function initializeHashUi() {
  setHashButtonBusy(false);
  if (dom.btnCopyHash) {
    dom.btnCopyHash.disabled = true;
  }
}
