import { state } from "../state.js";
import { isServerAuthorized, sessionScopedUrl, setServerFeatureAvailability } from "../runtime.js";
import { fetchJson, requireInventoryDeps, setStatus } from "./context.js";
import {
  applyActivationFilters,
  normalizeActivationRows,
  renderActivationMessage,
  syncActivationFilterOptions,
  withActivationSearchTarget,
} from "./activation_view.js";
import { updateCurrentObjectActivationState } from "./policy_object.js";
import { readActivationScopeInputs, updateActivationScopeLabel } from "./world_scope.js";

async function buildActivationStatusMap(rows) {
  const policyTypes = Array.from(
    new Set(
      (rows || [])
        .map((row) => String(row?.policyType || "").trim())
        .filter(Boolean)
    )
  );
  if (!policyTypes.length) {
    return new Map();
  }

  try {
    const payloadGroups = await Promise.all(
      policyTypes.map(async (policyType) => {
        const query = new URLSearchParams({ policy_type: policyType });
        const payload = await fetchJson(
          sessionScopedUrl(`/api/policies?${query.toString()}`)
        );
        return Array.isArray(payload?.items) ? payload.items : [];
      })
    );

    const detailsBySelector = new Map();
    for (const group of payloadGroups) {
      for (const item of group) {
        const selector = `${String(item?.policy_id || "").trim()}:${String(item?.variant || "").trim()}`;
        const status = String(item?.status || "").trim();
        const updatedAt = String(item?.updated_at || "").trim();
        if (!selector || !status) {
          continue;
        }
        detailsBySelector.set(selector, {
          status,
          updatedAt,
        });
      }
    }
    return detailsBySelector;
  } catch (_error) {
    return new Map();
  }
}

async function renderActivationScopePayload(payload) {
  state.latestActivationPayload = payload;
  state.activationColumnWidths = null;
  const baseRows = normalizeActivationRows(
    Array.isArray(payload?.items) ? payload.items : []
  );
  const detailsBySelector = await buildActivationStatusMap(baseRows);
  state.activationRows = baseRows.map((row) =>
    withActivationSearchTarget({
      ...row,
      status: detailsBySelector.get(row.selector)?.status || "unknown",
      updatedAt: detailsBySelector.get(row.selector)?.updatedAt || "",
    })
  );
  updateCurrentObjectActivationState();
  syncActivationFilterOptions(state.activationRows);
  applyActivationFilters();
  setServerFeatureAvailability();
}

export async function refreshActivationScope({ silent = false } = {}) {
  requireInventoryDeps();
  if (!isServerAuthorized()) {
    renderActivationMessage("Activation mapping requires an admin/superuser session.");
    if (!silent) {
      setStatus("Activation mapping unavailable: admin/superuser session required.");
    }
    return null;
  }

  const { worldId, scope } = readActivationScopeInputs();
  updateActivationScopeLabel();
  if (!worldId) {
    renderActivationMessage("Select a world before loading activation mappings.", "warning");
    if (!silent) {
      setStatus("Activation mapping load skipped: world selection is required.");
    }
    return null;
  }

  if (!silent) {
    setStatus(`Loading activation mappings for scope ${scope}...`);
  }
  try {
    const query = new URLSearchParams({
      scope,
      effective: "true",
    });
    const payload = await fetchJson(
      sessionScopedUrl(`/api/policy-activations-live?${query.toString()}`)
    );
    await renderActivationScopePayload(payload);
    if (!silent) {
      const itemCount = Array.isArray(payload?.items) ? payload.items.length : 0;
      setStatus(`Activation mappings loaded for ${scope} (${itemCount} entries).`);
    }
    return payload;
  } catch (error) {
    if (!silent) {
      setStatus(`Activation mapping load failed: ${error.message}`);
    }
    return null;
  }
}
