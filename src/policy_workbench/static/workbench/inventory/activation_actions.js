import { dom } from "../dom.js";
import { state } from "../state.js";
import { isServerAuthorized, sessionScopedUrl, setServerFeatureAvailability } from "../runtime.js";
import { fetchJson, requireInventoryDeps, setStatus } from "./context.js";
import {
  getSelectedActivationRow,
  setSelectedActivationRow,
  updateActivationStatusActionState,
} from "./activation_view.js";
import { refreshActivationScope } from "./activation_scope.js";
import { loadPolicyObject } from "./policy_inventory.js";

export async function applySelectedActivationStatus() {
  requireInventoryDeps();
  if (!isServerAuthorized()) {
    setStatus("Status update unavailable: admin/superuser session required.");
    return;
  }

  const selectedRow = getSelectedActivationRow();
  if (!selectedRow) {
    setStatus("Select a mapping row before applying a status change.");
    return;
  }

  const nextStatus = String(dom.activationSetStatus?.value || "").trim();
  if (!nextStatus) {
    setStatus("Choose a target status before applying.");
    return;
  }
  if (nextStatus === String(selectedRow.status || "").trim()) {
    setStatus(`Selected mapping is already ${nextStatus}.`);
    return;
  }

  setStatus(`Applying status ${nextStatus} to ${selectedRow.policyId}:${selectedRow.variant}...`);
  try {
    const query = new URLSearchParams({ variant: selectedRow.variant });
    const detailPayload = await fetchJson(
      sessionScopedUrl(`/api/policies/${encodeURIComponent(selectedRow.policyId)}?${query.toString()}`)
    );
    const savePayload = {
      policy_type: selectedRow.policyType,
      namespace: selectedRow.namespace,
      policy_key: selectedRow.policyKey,
      variant: selectedRow.variant,
      raw_content: JSON.stringify(detailPayload.content || {}, null, 2),
      schema_version: String(detailPayload.schema_version || "1.0").trim() || "1.0",
      status: nextStatus,
      activate: false,
    };

    const saveResult = await fetchJson("/api/policy-save", {
      method: "POST",
      body: JSON.stringify(savePayload),
    });

    await refreshActivationScope({ silent: true });
    setSelectedActivationRow(selectedRow.selector);
    if (
      state.selectedPolicyRecord
      && String(state.selectedPolicyRecord.policy_id || "").trim() === selectedRow.policyId
      && String(state.selectedPolicyRecord.variant || "").trim() === selectedRow.variant
    ) {
      await loadPolicyObject(selectedRow.policyId, selectedRow.variant);
    }
    setStatus(
      `Status updated for ${selectedRow.policyId}:${selectedRow.variant} to ${nextStatus} (v${saveResult.policy_version}).`
    );
  } catch (error) {
    setStatus(`Status update failed: ${error.message}`);
  } finally {
    updateActivationStatusActionState();
    setServerFeatureAvailability();
  }
}
