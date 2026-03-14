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


def test_package_data_patterns_cover_runtime_templates_and_static_assets() -> None:
    """Package-data patterns should include all shipped runtime template/static assets."""

    repo_root = Path(__file__).resolve().parents[2]
    package_root = repo_root / "src" / "policy_workbench"
    pyproject_path = repo_root / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    package_data = (
        data.get("tool", {})
        .get("setuptools", {})
        .get("package-data", {})
        .get("policy_workbench", [])
    )
    patterns = [str(item) for item in package_data]

    required_runtime_files = [
        "templates/index.html",
        "static/workbench.css",
        "static/pipe-works-base.css",
        "static/workbench.js",
    ]
    required_runtime_files.extend(
        path.relative_to(package_root).as_posix()
        for path in sorted((package_root / "static" / "workbench").glob("*.js"))
    )

    missing: list[str] = []
    for relative_path in required_runtime_files:
        if not any(Path(relative_path).match(pattern) for pattern in patterns):
            missing.append(relative_path)

    assert not missing, f"Runtime assets not covered by package-data patterns: {missing}"
