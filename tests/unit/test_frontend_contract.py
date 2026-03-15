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
_WORKBENCH_INVENTORY = _WORKBENCH_MODULE_DIR / "inventory.js"
_WORKBENCH_RUNTIME = _WORKBENCH_MODULE_DIR / "runtime.js"
_WORKBENCH_RUNTIME_SESSION = _WORKBENCH_MODULE_DIR / "runtime_session.js"
_WORKBENCH_BOOT = _WORKBENCH_MODULE_DIR / "boot.js"
_WORKBENCH_EDITOR_ACTIONS = _WORKBENCH_MODULE_DIR / "editor_actions.js"
_WORKBENCH_TABS = _WORKBENCH_MODULE_DIR / "tabs.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _template_ids() -> set[str]:
    return set(re.findall(r'id="([A-Za-z0-9_-]+)"', _read(_TEMPLATE_PATH)))


def _js_get_element_ids() -> set[str]:
    ids: set[str] = set()
    for path in [_WORKBENCH_ENTRY, *_WORKBENCH_MODULE_DIR.glob("*.js")]:
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
        + _read(_WORKBENCH_INVENTORY)
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
        + _read(_WORKBENCH_INVENTORY)
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
