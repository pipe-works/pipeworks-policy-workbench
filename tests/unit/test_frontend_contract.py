"""Frontend contract tests for template/JavaScript DOM wiring."""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE_PATH = _REPO_ROOT / "src" / "policy_workbench" / "templates" / "index.html"
_WORKBENCH_STATIC = _REPO_ROOT / "src" / "policy_workbench" / "static"
_WORKBENCH_ENTRY = _WORKBENCH_STATIC / "workbench.js"
_WORKBENCH_MODULE_DIR = _WORKBENCH_STATIC / "workbench"
_WORKBENCH_APP = _WORKBENCH_MODULE_DIR / "app.js"
_WORKBENCH_DOM = _WORKBENCH_MODULE_DIR / "dom.js"
_WORKBENCH_INVENTORY_FACADE = _WORKBENCH_MODULE_DIR / "inventory.js"
_WORKBENCH_INVENTORY_DIR = _WORKBENCH_MODULE_DIR / "inventory"
_WORKBENCH_RUNTIME = _WORKBENCH_MODULE_DIR / "runtime.js"
_WORKBENCH_RUNTIME_SESSION = _WORKBENCH_MODULE_DIR / "runtime_session.js"
_WORKBENCH_BOOT = _WORKBENCH_MODULE_DIR / "boot.js"
_WORKBENCH_EDITOR_ACTIONS = _WORKBENCH_MODULE_DIR / "editor_actions.js"
_WORKBENCH_TABS = _WORKBENCH_MODULE_DIR / "tabs.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _inventory_sources() -> str:
    sources = [_read(_WORKBENCH_INVENTORY_FACADE)]
    for path in sorted(_WORKBENCH_INVENTORY_DIR.glob("*.js")):
        sources.append(_read(path))
    return "".join(sources)


def _template_ids() -> set[str]:
    return set(re.findall(r'id="([A-Za-z0-9_-]+)"', _read(_TEMPLATE_PATH)))


def _js_get_element_ids() -> set[str]:
    ids: set[str] = set()
    for path in [
        _WORKBENCH_ENTRY,
        *_WORKBENCH_MODULE_DIR.glob("*.js"),
        *_WORKBENCH_INVENTORY_DIR.glob("*.js"),
    ]:
        ids.update(re.findall(r'getElementById\("([A-Za-z0-9_-]+)"\)', _read(path)))
    return ids


def _dom_keys() -> list[str]:
    dom_source = _read(_WORKBENCH_DOM)
    return re.findall(r"^\s*([A-Za-z0-9_]+):\s*document\.getElementById", dom_source, flags=re.M)


def test_all_js_get_element_ids_exist_in_template() -> None:
    """Every JS ``getElementById`` target should exist in ``index.html``."""
    missing = sorted(_js_get_element_ids() - _template_ids())
    assert not missing, f"JS references IDs missing from template: {missing}"


def test_dom_keys_are_used_by_app_module() -> None:
    """Every key declared in ``dom.js`` should be consumed by workbench modules."""
    consumer_sources = (
        _read(_WORKBENCH_APP)
        + _read(_WORKBENCH_RUNTIME)
        + _inventory_sources()
        + _read(_WORKBENCH_RUNTIME_SESSION)
        + _read(_WORKBENCH_BOOT)
        + _read(_WORKBENCH_EDITOR_ACTIONS)
        + _read(_WORKBENCH_TABS)
    )
    unused = sorted(key for key in _dom_keys() if f"dom.{key}" not in consumer_sources)
    assert not unused, f"Unused DOM keys in dom.js: {unused}"


def test_legacy_runtime_label_hooks_are_not_reintroduced() -> None:
    """Legacy runtime label hooks should not reappear without matching template support."""
    combined = (
        _read(_WORKBENCH_ENTRY)
        + _read(_WORKBENCH_APP)
        + _inventory_sources()
        + _read(_WORKBENCH_RUNTIME)
        + _read(_WORKBENCH_RUNTIME_SESSION)
        + _read(_WORKBENCH_BOOT)
        + _read(_WORKBENCH_EDITOR_ACTIONS)
        + _read(_WORKBENCH_DOM)
    )
    assert "runtime-mode-url-label" not in combined
    assert "runtime-auth-label" not in combined


def test_runtime_mode_switch_does_not_implicitly_override_server_url() -> None:
    """Mode-switch requests should not reuse typed URL unless explicitly applied."""

    runtime_session = _read(_WORKBENCH_RUNTIME_SESSION)
    assert "selectedRuntimeModeServerUrl" not in runtime_session
    assert "if (explicitServerUrl !== null)" in runtime_session


def test_world_dropdown_uses_canonical_api_name_without_id_suffix() -> None:
    """World selector labels should not append transformed IDs when name is present."""

    inventory_source = _inventory_sources()
    assert "${worldName} (${worldId})" not in inventory_source


def test_inventory_renders_table_rows_for_policy_list() -> None:
    """Inventory renderer should build table-based policy rows."""

    template_source = _read(_TEMPLATE_PATH)
    inventory_source = _inventory_sources()
    assert 'id="inventory-list"' in template_source
    assert "inventory-table" in inventory_source
    assert 'document.createElement("table")' in inventory_source


def test_editor_view_renders_canonical_json_content_for_policy_objects() -> None:
    """Editor rendering should preserve canonical object shape from mud-server payloads."""

    inventory_source = _inventory_sources()
    assert "return JSON.stringify(content, null, 2);" in inventory_source
    assert 'return String(content.text || "");' not in inventory_source
    assert 'return buildSpeciesYamlFromText(content.text || "");' not in inventory_source


def test_editor_controls_expose_edit_and_close_actions() -> None:
    """Editor controls should include explicit edit-mode entry/exit actions."""

    template_source = _read(_TEMPLATE_PATH)
    assert 'id="btn-edit-file"' in template_source
    assert 'id="btn-close-file"' in template_source
    assert 'id="save-scope-mode"' in template_source
    assert 'id="save-rollout-all-worlds"' in template_source


def test_editor_actions_support_world_scoped_rollout_activation() -> None:
    """Editor save flow should support world-scoped activation rollout calls."""

    editor_actions_source = _read(_WORKBENCH_EDITOR_ACTIONS)
    assert '"/api/policy-activation-set"' in editor_actions_source
    assert "buildScopedVariantName" in editor_actions_source
    assert "rolloutVariantToOtherWorlds" in editor_actions_source


def test_activation_view_renders_table_with_filters() -> None:
    """Activation mappings should render as a filterable table, not report chips."""

    template_source = _read(_TEMPLATE_PATH)
    inventory_source = _inventory_sources()
    assert 'id="activation-filter-policy-type"' in template_source
    assert 'id="activation-filter-namespace"' in template_source
    assert 'id="activation-filter-status"' in template_source
    assert 'id="activation-filter-search"' in template_source
    assert 'id="activation-set-status"' in template_source
    assert 'id="btn-activation-apply-status"' in template_source
    assert "Activation mappings table" in inventory_source
    assert "applyActivationFilters" in inventory_source
    assert "applySelectedActivationStatus" in inventory_source
    assert "renderSelectOptionsWithCounts" in inventory_source
    assert "activation-table__resize-handle" in inventory_source
    assert '"Mapped At"' in inventory_source
    assert '"Updated At"' in inventory_source


def test_species_block_editor_view_renders_canonical_json_content() -> None:
    """Species blocks should render canonical object JSON in editor view."""
    inventory_source = _inventory_sources()
    assert 'return buildSpeciesYamlFromText(content.text || "");' not in inventory_source


def test_clothing_block_is_in_authorable_policy_type_set() -> None:
    """Clothing blocks should be editable through the policy workbench authoring flow."""

    inventory_source = _inventory_sources()
    authorable_set_match = re.search(
        r"const AUTHORABLE_POLICY_TYPES = new Set\(\[(.*?)\]\);",
        inventory_source,
        flags=re.S,
    )
    assert authorable_set_match is not None
    assert '"clothing_block"' in authorable_set_match.group(1)


def test_inventory_facade_export_contract_is_stable() -> None:
    """Facade exports should remain stable while implementation modules move."""

    facade_source = _read(_WORKBENCH_INVENTORY_FACADE)
    exported_names: set[str] = set()
    for block in re.findall(r"export\s+\{([^}]+)\}\s+from", facade_source, flags=re.S):
        for raw_name in block.split(","):
            normalized = raw_name.strip()
            if not normalized:
                continue
            exported_names.add(normalized.split(" as ")[0].strip())

    expected_exports = {
        "configureInventory",
        "setEditorReadOnlyMode",
        "setAvailableWorldOptions",
        "clearAvailableWorldOptions",
        "refreshPolicyNamespaceOptions",
        "refreshPolicyFilterOptions",
        "buildPolicySelectorLabel",
        "renderPolicyInventory",
        "refreshPolicyInventory",
        "loadPolicyObject",
        "readActivationScopeInputs",
        "updateActivationScopeLabel",
        "updateActivationSaveSummary",
        "renderActivationMessage",
        "updateActivationStatusActionState",
        "applySelectedActivationStatus",
        "applyActivationFilters",
        "refreshActivationScope",
        "renderUnauthorizedServerState",
    }
    assert exported_names == expected_exports
    assert "export function " not in facade_source
