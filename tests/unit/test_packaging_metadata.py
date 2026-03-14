"""Unit tests for packaging metadata contracts."""

from __future__ import annotations

import tomllib
from pathlib import Path


def test_package_data_includes_nested_workbench_js_modules() -> None:
    """Setuptools package data should include nested workbench module assets."""

    repo_root = Path(__file__).resolve().parents[2]
    pyproject_path = repo_root / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    package_data = (
        data.get("tool", {})
        .get("setuptools", {})
        .get("package-data", {})
        .get("policy_workbench", [])
    )
    normalized = [str(item) for item in package_data]

    assert "static/workbench/*.js" in normalized


def test_package_data_patterns_cover_all_existing_workbench_modules() -> None:
    """Current package-data patterns should match every existing nested JS module."""

    repo_root = Path(__file__).resolve().parents[2]
    pyproject_path = repo_root / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    package_data = (
        data.get("tool", {})
        .get("setuptools", {})
        .get("package-data", {})
        .get("policy_workbench", [])
    )
    patterns = [str(item) for item in package_data]

    workbench_dir = repo_root / "src" / "policy_workbench" / "static" / "workbench"
    existing_relative = [
        path.relative_to(repo_root / "src" / "policy_workbench").as_posix()
        for path in sorted(workbench_dir.glob("*.js"))
    ]
    assert existing_relative, "Expected at least one nested workbench JS module."

    missing: list[str] = []
    for relative_path in existing_relative:
        if not any(Path(relative_path).match(pattern) for pattern in patterns):
            missing.append(relative_path)

    assert not missing, f"Unmatched nested JS modules in package-data patterns: {missing}"
