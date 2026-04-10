"""Focused diagnostics/hash service helpers for web routes.

This module isolates diagnostics-heavy behavior so ``web_services`` can remain
an orchestration layer while Phase 2 decomposition completes.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pipeworks_ipc.hashing import compute_payload_hash

from .models import PolicyTreeSnapshot
from .web_models import HashCanonicalResponse

_EDITOR_FILE_SUFFIXES = {".txt", ".yaml", ".yml", ".json"}
_HASH_VERSION = "policy_tree_hash_v1"
_DEFAULT_CANONICAL_HASH_URL = "http://127.0.0.1:8000/api/policy/hash-snapshot"
_CANONICAL_HASH_URL_ENV = "PW_POLICY_HASH_SNAPSHOT_URL"

ipc_hashing: Any | None
try:
    import pipeworks_ipc.hashing as ipc_hashing
except ImportError:  # pragma: no cover - import path is expected in normal runtime
    ipc_hashing = None


@dataclass(frozen=True, slots=True)
class PolicyHashEntry:
    """One normalized local policy file entry used for hash calculations."""

    relative_path: str
    content_hash: str


def resolve_canonical_hash_snapshot_url(
    url_override: str | None,
    *,
    canonical_hash_url_env: str = _CANONICAL_HASH_URL_ENV,
    default_canonical_hash_url: str = _DEFAULT_CANONICAL_HASH_URL,
) -> str:
    """Resolve canonical hash snapshot URL from override, env var, or default."""

    candidate = url_override or os.getenv(canonical_hash_url_env) or default_canonical_hash_url
    normalized = (candidate or "").strip()
    if not normalized:
        raise ValueError("Canonical hash snapshot URL must not be empty")
    return normalized


def fetch_canonical_hash_snapshot(
    url: str,
    *,
    opener=urlopen,
    response_model=HashCanonicalResponse,
) -> HashCanonicalResponse:
    """Fetch and validate canonical mud-server hash snapshot payload."""

    request = Request(url=url, headers={"Accept": "application/json"})
    try:
        with opener(request, timeout=5.0) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to fetch canonical hash snapshot from {url}: {exc}") from exc

    validated = response_model.model_validate(payload)
    if not isinstance(validated, response_model):
        raise ValueError(f"Canonical hash snapshot from {url} did not match expected schema")
    return cast(HashCanonicalResponse, validated)


def collect_local_policy_entries(policy_root: Path) -> list[PolicyHashEntry]:
    """Collect deterministic policy file hash entries from ``policy_root``."""

    entries: list[PolicyHashEntry] = []
    for path in sorted(policy_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _EDITOR_FILE_SUFFIXES:
            continue

        relative_path = normalize_relative_path(path.relative_to(policy_root).as_posix())
        entries.append(
            PolicyHashEntry(
                relative_path=relative_path,
                content_hash=compute_file_hash(relative_path, path.read_bytes()),
            )
        )

    return entries


def compute_file_hash(
    relative_path: str,
    content_bytes: bytes,
    *,
    ipc_hashing_module=ipc_hashing,
    hash_version: str = _HASH_VERSION,
) -> str:
    """Compute deterministic policy file hash using IPC as primary contract."""

    helper = (
        getattr(ipc_hashing_module, "compute_policy_file_hash", None)
        if ipc_hashing_module
        else None
    )
    if callable(helper):
        return str(helper(relative_path, content_bytes))

    normalized_path = normalize_relative_path(relative_path)
    return str(
        compute_payload_hash(
            {
                "hash_version": hash_version,
                "relative_path": normalized_path,
                "content_bytes_hex": content_bytes.hex(),
            }
        )
    )


def compute_tree_hash(
    *,
    entries: list[PolicyHashEntry],
    ipc_hashing_module=ipc_hashing,
    hash_version: str = _HASH_VERSION,
) -> str:
    """Compute deterministic policy tree hash using IPC as primary contract."""

    helper = (
        getattr(ipc_hashing_module, "compute_policy_tree_hash", None)
        if ipc_hashing_module
        else None
    )
    entry_cls = getattr(ipc_hashing_module, "PolicyHashEntry", None) if ipc_hashing_module else None
    if callable(helper) and entry_cls is not None:
        ipc_entries = [
            entry_cls(relative_path=entry.relative_path, content_hash=entry.content_hash)
            for entry in entries
        ]
        return str(helper(ipc_entries))

    payload_entries = [
        {
            "relative_path": normalize_relative_path(entry.relative_path),
            "content_hash": entry.content_hash,
        }
        for entry in entries
    ]
    # Sort before hashing to make fallback behavior independent of filesystem
    # traversal order or caller-provided entry ordering.
    payload_entries.sort(key=lambda item: str(item["relative_path"]))
    return str(compute_payload_hash({"hash_version": hash_version, "entries": payload_entries}))


def compute_missing_content_hash(
    relative_path: str,
    *,
    hash_version: str = _HASH_VERSION,
) -> str:
    """Build deterministic hash marker for missing canonical-managed files."""

    normalized_path = normalize_relative_path(relative_path)
    return str(
        compute_payload_hash(
            {
                "hash_version": hash_version,
                "relative_path": normalized_path,
                "missing": True,
            }
        )
    )


def normalize_relative_path(relative_path: str) -> str:
    """Normalize a policy-relative path and reject traversal-like values."""

    as_posix = PurePosixPath(relative_path.replace("\\", "/")).as_posix()
    if as_posix.startswith("../") or "/../" in f"/{as_posix}":
        raise ValueError(f"Policy relative path must not traverse upwards: {relative_path!r}")

    normalized = as_posix.lstrip("./")
    if normalized in {"", "."}:
        raise ValueError("Policy relative path must not be empty")
    return normalized


def is_supported_editor_file(
    relative_path: str,
    *,
    editor_file_suffixes: set[str] | tuple[str, ...] = _EDITOR_FILE_SUFFIXES,
) -> bool:
    """Return whether ``relative_path`` is supported by the web editor."""

    return Path(relative_path).suffix.lower() in set(editor_file_suffixes)


def validate_supported_editor_path(
    relative_path: str,
    *,
    editor_file_suffixes: set[str] | tuple[str, ...] = _EDITOR_FILE_SUFFIXES,
) -> None:
    """Raise ``ValueError`` when path is unsupported for web editor operations."""

    if not is_supported_editor_file(
        relative_path,
        editor_file_suffixes=editor_file_suffixes,
    ):
        raise ValueError(
            "Only .txt, .yaml, .yml, and .json policy files are supported by the web editor"
        )


def filter_snapshot_to_supported_files(
    snapshot: PolicyTreeSnapshot,
    *,
    editor_file_suffixes: set[str] | tuple[str, ...] = _EDITOR_FILE_SUFFIXES,
) -> PolicyTreeSnapshot:
    """Return snapshot narrowed to files supported by the web workbench editor."""

    supported_artifacts = [
        artifact
        for artifact in snapshot.artifacts
        if is_supported_editor_file(
            artifact.relative_path,
            editor_file_suffixes=editor_file_suffixes,
        )
    ]
    return PolicyTreeSnapshot(
        root=snapshot.root,
        directories=snapshot.directories,
        artifacts=supported_artifacts,
    )


def read_optional_text(path: Path | None) -> str | None:
    """Read UTF-8 text from ``path`` when available, otherwise return ``None``."""

    if path is None:
        return None
    if not path.exists() or not path.is_file():
        return None

    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"Unable to read text for diff: {path} ({exc})") from exc
