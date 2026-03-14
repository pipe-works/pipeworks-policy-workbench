"""Focused local policy metadata helper services for web routes.

This module isolates local canonical policy-type/status/namespace discovery
fallback behavior so ``web_services`` can keep narrowing toward orchestration.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Protocol


class PolicySelectorLike(Protocol):
    """Selector contract needed by local namespace derivation."""

    @property
    def policy_type(self) -> str: ...

    @property
    def namespace(self) -> str: ...


class ConstantSetLoader(Protocol):
    """Callable contract for loading one constant set from source."""

    def __call__(
        self,
        *,
        source_path: Path,
        constant_name: str,
    ) -> list[str] | None: ...


def resolve_local_policy_types_source_path(*, local_policy_types_file_env: str) -> Path | None:
    """Resolve local canonical policy-type source file path."""
    override = (os.getenv(local_policy_types_file_env, "") or "").strip()
    if override:
        return Path(override).expanduser()

    workspace_root = Path(__file__).resolve().parents[3]
    return (
        workspace_root
        / "pipeworks_mud_server"
        / "src"
        / "mud_server"
        / "services"
        / "policy_service.py"
    )


def load_local_constant_set_values(*, source_path: Path, constant_name: str) -> list[str] | None:
    """Load one module-level set constant list from a Python source file."""
    if not source_path.exists():
        return None
    try:
        text = source_path.read_text(encoding="utf-8")
    except OSError:
        return None
    pattern = rf"{re.escape(constant_name)}\s*=\s*{{(?P<body>[^}}]*)}}"
    match = re.search(pattern, text, flags=re.DOTALL)
    if match is None:
        return None
    return re.findall(r"['\"]([^'\"]+)['\"]", match.group("body"))


def load_local_policy_types_from_disk(
    *,
    fallback_policy_types: tuple[str, ...],
    resolve_source_path: Callable[[], Path | None],
    load_constant_set_values: ConstantSetLoader,
    dedupe_preserve_order: Callable[[list[str]], list[str]],
) -> tuple[list[str], str, str | None]:
    """Load canonical policy types from local mud-server source file."""
    source_path = resolve_source_path()
    if source_path is None:
        return (
            list(fallback_policy_types),
            "fallback",
            "Local mud-server canonical policy type source file was not found.",
        )

    values = load_constant_set_values(
        source_path=source_path,
        constant_name="_SUPPORTED_POLICY_TYPES",
    )
    if values is None:
        return (
            list(fallback_policy_types),
            "fallback",
            "Local policy type source file did not expose _SUPPORTED_POLICY_TYPES.",
        )

    parsed_policy_types = dedupe_preserve_order(values)
    if not parsed_policy_types:
        return (
            list(fallback_policy_types),
            "fallback",
            "Local policy type source file did not provide usable policy types.",
        )
    return (
        parsed_policy_types,
        "local_disk",
        f"Loaded canonical policy types from {source_path}.",
    )


def load_local_policy_statuses_from_disk(
    *,
    fallback_policy_statuses: tuple[str, ...],
    resolve_source_path: Callable[[], Path | None],
    load_constant_set_values: ConstantSetLoader,
    dedupe_preserve_order: Callable[[list[str]], list[str]],
) -> tuple[list[str], str, str | None]:
    """Load canonical policy statuses from local mud-server source file."""
    source_path = resolve_source_path()
    if source_path is None:
        return (
            list(fallback_policy_statuses),
            "fallback",
            "Local mud-server canonical policy status source file was not found.",
        )

    values = load_constant_set_values(
        source_path=source_path,
        constant_name="_SUPPORTED_STATUSES",
    )
    if values is None:
        return (
            list(fallback_policy_statuses),
            "fallback",
            "Local policy status source file did not expose _SUPPORTED_STATUSES.",
        )

    parsed_statuses = dedupe_preserve_order(values)
    if not parsed_statuses:
        return (
            list(fallback_policy_statuses),
            "fallback",
            "Local policy status source file did not provide usable statuses.",
        )
    return (
        parsed_statuses,
        "local_disk",
        f"Loaded canonical policy statuses from {source_path}.",
    )


def load_local_namespaces_from_disk(
    *,
    source_root: Path,
    policy_type: str | None,
    is_supported_editor_file: Callable[[str], bool],
    selector_from_relative_path: Callable[[str], PolicySelectorLike | None],
    dedupe_preserve_order: Callable[[list[str]], list[str]],
) -> list[str]:
    """Derive canonical namespace options from local authorable policy files."""
    if not source_root.exists() or not source_root.is_dir():
        return []

    namespaces: list[str] = []
    for path in sorted(source_root.rglob("*")):
        if not path.is_file():
            continue
        try:
            relative_path = path.relative_to(source_root).as_posix()
        except ValueError:
            continue
        if not is_supported_editor_file(relative_path):
            continue
        selector = selector_from_relative_path(relative_path)
        if selector is None:
            continue
        if policy_type and selector.policy_type != policy_type:
            continue
        namespaces.append(selector.namespace)
    return dedupe_preserve_order(namespaces)
