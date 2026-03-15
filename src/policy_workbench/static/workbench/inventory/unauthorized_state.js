import { state } from "../state.js";
import { runtimeAuthStatus } from "../runtime.js";
import { renderActivationMessage } from "./activation_view.js";
import { clearCurrentObjectPanel, setEditorReadOnlyMode } from "./policy_object.js";
import { renderPolicyInventory } from "./policy_inventory.js";

export function renderUnauthorizedServerState(runtimeAuth = null) {
  state.inventoryItems = [];
  state.selectedPolicyRecord = null;
  state.selectedArtifact = null;
  state.editorIsEditing = false;
  state.editorBaseContent = "";
  setEditorReadOnlyMode(true);
  renderPolicyInventory([]);
  clearCurrentObjectPanel();
  const status = runtimeAuth?.status || runtimeAuthStatus();
  if (status === "forbidden") {
    renderActivationMessage("Server mode connected, but session role is not admin/superuser.");
  } else if (status === "unauthenticated") {
    renderActivationMessage("Server mode connected, but session is invalid or expired.");
  } else {
    renderActivationMessage("Server mode connected, but no session id is configured.");
  }
}
