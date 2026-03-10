"""Pipeworks Policy Workbench package metadata."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

__all__ = ["__version__"]


def _resolve_version() -> str:
    """Return installed package version with a deterministic dev fallback."""

    try:
        return version("pipeworks-policy-workbench")
    except PackageNotFoundError:
        # Source-tree fallback for local execution before editable install.
        return "0.0.0-dev"


__version__ = _resolve_version()
