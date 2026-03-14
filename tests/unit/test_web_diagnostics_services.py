"""Unit tests for extracted diagnostics/hash web service helpers."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from policy_workbench import web_diagnostics_services
from policy_workbench.sync_models import (
    MirrorMap,
    MirrorTarget,
    SyncAction,
    SyncActionType,
    SyncPlan,
)
from policy_workbench.web_models import HashCanonicalResponse, HashDirectoryResponse


def test_compute_tree_hash_is_order_stable() -> None:
    """Tree hash should be deterministic regardless of input entry order."""

    entries_a = [
        web_diagnostics_services.PolicyHashEntry(
            relative_path="image/prompts/b.txt",
            content_hash="h2",
        ),
        web_diagnostics_services.PolicyHashEntry(
            relative_path="image/prompts/a.txt",
            content_hash="h1",
        ),
    ]
    entries_b = list(reversed(entries_a))

    hash_a = web_diagnostics_services.compute_tree_hash(entries=entries_a, ipc_hashing_module=None)
    hash_b = web_diagnostics_services.compute_tree_hash(entries=entries_b, ipc_hashing_module=None)
    assert hash_a == hash_b

    hash_changed = web_diagnostics_services.compute_tree_hash(
        entries=[
            web_diagnostics_services.PolicyHashEntry(
                relative_path="image/prompts/a.txt",
                content_hash="h1-modified",
            ),
            web_diagnostics_services.PolicyHashEntry(
                relative_path="image/prompts/b.txt",
                content_hash="h2",
            ),
        ],
        ipc_hashing_module=None,
    )
    assert hash_changed != hash_a


def test_collect_local_policy_entries_filters_supported_files(tmp_path: Path) -> None:
    """Entry collector should include only supported editor suffixes in sorted order."""

    root = tmp_path / "policy-root"
    (root / "image" / "prompts").mkdir(parents=True)
    (root / "image" / "prompts" / "scene.txt").write_text("scene", encoding="utf-8")
    (root / "image" / "prompts" / "notes.md").write_text("ignore", encoding="utf-8")
    (root / "image" / "blocks").mkdir(parents=True)
    (root / "image" / "blocks" / "goblin.yaml").write_text("text: goblin", encoding="utf-8")

    entries = web_diagnostics_services.collect_local_policy_entries(root)
    assert [entry.relative_path for entry in entries] == [
        "image/blocks/goblin.yaml",
        "image/prompts/scene.txt",
    ]


def test_compute_missing_content_hash_normalizes_path_and_rejects_traversal() -> None:
    """Missing-entry hash helper should normalize equivalent paths and reject escapes."""

    hash_a = web_diagnostics_services.compute_missing_content_hash("./image/prompts/scene.txt")
    hash_b = web_diagnostics_services.compute_missing_content_hash("image/prompts/scene.txt")
    assert hash_a == hash_b

    with pytest.raises(ValueError, match="must not traverse upwards"):
        web_diagnostics_services.compute_missing_content_hash("../outside.txt")


def test_build_sync_payload_and_apply_plan_filter_to_supported_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Sync payload/apply-plan helpers should filter out unsupported file suffixes."""

    source_root = tmp_path / "source"
    source_root.mkdir(parents=True)
    target_root = tmp_path / "target"
    target_root.mkdir(parents=True)

    plan = SyncPlan(
        source_root=source_root,
        map_path=tmp_path / "mirror_map.yaml",
        actions=[
            SyncAction(
                target_name="target-a",
                relative_path="image/prompts/scene.txt",
                action=SyncActionType.CREATE,
                source_path=source_root / "image/prompts/scene.txt",
                target_path=target_root / "image/prompts/scene.txt",
            ),
            SyncAction(
                target_name="target-a",
                relative_path="image/prompts/same.txt",
                action=SyncActionType.UNCHANGED,
                source_path=source_root / "image/prompts/same.txt",
                target_path=target_root / "image/prompts/same.txt",
            ),
            SyncAction(
                target_name="target-a",
                relative_path="image/prompts/notes.md",
                action=SyncActionType.UPDATE,
                source_path=source_root / "image/prompts/notes.md",
                target_path=target_root / "image/prompts/notes.md",
            ),
        ],
    )

    mirror_map = MirrorMap(
        config_path=tmp_path / "mirror_map.yaml",
        source_root=source_root,
        targets=[MirrorTarget(name="target-a", root=target_root)],
    )

    monkeypatch.setattr(
        web_diagnostics_services,
        "resolve_mirror_map_path",
        lambda explicit_map_path=None: tmp_path / "mirror_map.yaml",
    )
    monkeypatch.setattr(web_diagnostics_services, "load_mirror_map", lambda _path: mirror_map)
    monkeypatch.setattr(web_diagnostics_services, "build_sync_plan", lambda **_kwargs: plan)

    payload = web_diagnostics_services.build_sync_payload(
        source_root=source_root,
        map_path_override=None,
        include_unchanged=False,
    )
    assert payload.counts == {"create": 1, "update": 0, "unchanged": 1, "target_only": 0}
    assert [action.relative_path for action in payload.actions] == ["image/prompts/scene.txt"]

    filtered_plan = web_diagnostics_services.build_sync_plan_for_apply(
        source_root=source_root,
        map_path_override=None,
    )
    assert [action.relative_path for action in filtered_plan.actions] == [
        "image/prompts/scene.txt",
        "image/prompts/same.txt",
    ]


def test_build_sync_compare_payload_groups_variants_and_prioritizes_focus_target(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Compare payload should group signatures and prioritize the focused target first."""

    source_root = tmp_path / "source"
    source_file = source_root / "image/prompts/scene.txt"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("canonical", encoding="utf-8")

    target_a_root = tmp_path / "target-a"
    target_b_root = tmp_path / "target-b"
    (target_a_root / "image/prompts").mkdir(parents=True)
    (target_b_root / "image/prompts").mkdir(parents=True)
    (target_a_root / "image/prompts/scene.txt").write_text("canonical", encoding="utf-8")

    plan = SyncPlan(
        source_root=source_root,
        map_path=tmp_path / "mirror_map.yaml",
        actions=[
            SyncAction(
                target_name="target-a",
                relative_path="image/prompts/scene.txt",
                action=SyncActionType.UNCHANGED,
                source_path=source_file,
                target_path=target_a_root / "image/prompts/scene.txt",
            ),
            SyncAction(
                target_name="target-b",
                relative_path="image/prompts/scene.txt",
                action=SyncActionType.CREATE,
                source_path=source_file,
                target_path=target_b_root / "image/prompts/scene.txt",
            ),
        ],
    )
    mirror_map = MirrorMap(
        config_path=tmp_path / "mirror_map.yaml",
        source_root=source_root,
        targets=[
            MirrorTarget(name="target-a", root=target_a_root),
            MirrorTarget(name="target-b", root=target_b_root),
        ],
    )

    monkeypatch.setattr(
        web_diagnostics_services,
        "resolve_mirror_map_path",
        lambda explicit_map_path=None: tmp_path / "mirror_map.yaml",
    )
    monkeypatch.setattr(web_diagnostics_services, "load_mirror_map", lambda _path: mirror_map)
    monkeypatch.setattr(web_diagnostics_services, "build_sync_plan", lambda **_kwargs: plan)

    payload = web_diagnostics_services.build_sync_compare_payload(
        source_root=source_root,
        map_path_override=None,
        relative_path="image/prompts/scene.txt",
        focus_target="target-b",
    )
    assert payload.unique_variant_count == 2
    assert payload.variants[0].kind == "source"
    assert payload.variants[1].target == "target-b"
    assert payload.variants[2].target == "target-a"
    assert payload.variants[2].matches_source is True


def test_build_hash_status_payload_handles_unavailable_and_drift_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Hash status should report canonical-unavailable and drift states deterministically."""

    source_root = tmp_path / "source"
    source_file = source_root / "image/prompts/scene.txt"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("canonical", encoding="utf-8")

    target_ok_root = tmp_path / "target-ok"
    target_drift_root = tmp_path / "target-drift"
    (target_ok_root / "image/prompts").mkdir(parents=True)
    (target_drift_root / "image/prompts").mkdir(parents=True)
    (target_ok_root / "image/prompts/scene.txt").write_text("canonical", encoding="utf-8")
    (target_drift_root / "image/prompts/scene.txt").write_text("drifted", encoding="utf-8")

    mirror_map = MirrorMap(
        config_path=tmp_path / "mirror_map.yaml",
        source_root=source_root,
        targets=[
            MirrorTarget(name="target-ok", root=target_ok_root),
            MirrorTarget(name="target-drift", root=target_drift_root),
        ],
    )
    monkeypatch.setattr(
        web_diagnostics_services,
        "resolve_mirror_map_path",
        lambda explicit_map_path=None: tmp_path / "mirror_map.yaml",
    )
    monkeypatch.setattr(web_diagnostics_services, "load_mirror_map", lambda _path: mirror_map)

    monkeypatch.setattr(
        web_diagnostics_services,
        "fetch_canonical_hash_snapshot",
        lambda _url: (_ for _ in ()).throw(ValueError("canonical unavailable")),
    )
    unavailable = web_diagnostics_services.build_hash_status_payload(
        source_root=source_root,
        map_path_override=None,
        canonical_snapshot_url_override="http://canonical.local/api",
    )
    assert unavailable.status == "canonical_unavailable"
    assert unavailable.canonical is None
    assert "canonical unavailable" in (unavailable.canonical_error or "")
    assert unavailable.targets[0].matches_canonical is None

    source_entries = web_diagnostics_services.collect_local_policy_entries(source_root)
    canonical_root_hash = web_diagnostics_services.compute_tree_hash(
        entries=source_entries,
        ipc_hashing_module=None,
    )
    canonical_snapshot = HashCanonicalResponse(
        hash_version="policy_tree_hash_v1",
        canonical_root=str(source_root),
        generated_at="2026-03-14T00:00:00Z",
        file_count=len(source_entries),
        root_hash=canonical_root_hash,
        directories=[HashDirectoryResponse(path="image/prompts", file_count=1, hash="dir-hash")],
    )
    monkeypatch.setattr(
        web_diagnostics_services,
        "fetch_canonical_hash_snapshot",
        lambda _url: canonical_snapshot,
    )
    drift = web_diagnostics_services.build_hash_status_payload(
        source_root=source_root,
        map_path_override=None,
        canonical_snapshot_url_override="http://canonical.local/api",
    )
    assert drift.status == "drift"
    assert any(target.matches_canonical is False for target in drift.targets)
    assert any(target.matches_canonical is True for target in drift.targets)


def test_fetch_canonical_hash_snapshot_success_and_error_paths() -> None:
    """Snapshot fetch helper should validate schema and transport failure branches."""

    class _FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

    payload = {
        "hash_version": "policy_tree_hash_v1",
        "canonical_root": "/tmp/source",
        "generated_at": "2026-03-10T12:00:00Z",
        "file_count": 1,
        "root_hash": "abc123",
        "directories": [],
    }
    snapshot = web_diagnostics_services.fetch_canonical_hash_snapshot(
        "http://canonical.local/api",
        opener=lambda request, timeout=5.0: _FakeResponse(payload),
    )
    assert snapshot.root_hash == "abc123"

    with pytest.raises(ValueError, match="Unable to fetch canonical hash snapshot"):
        web_diagnostics_services.fetch_canonical_hash_snapshot(
            "http://canonical.local/api",
            opener=lambda request, timeout=5.0: (_ for _ in ()).throw(OSError("down")),
        )


def test_misc_diagnostics_helpers_cover_branches(tmp_path: Path) -> None:
    """Small helper utilities should preserve deterministic branch behavior."""

    assert web_diagnostics_services.is_supported_editor_file("scene.yaml") is True
    assert web_diagnostics_services.is_supported_editor_file("scene.md") is False
    with pytest.raises(ValueError, match="Only .txt, .yaml, .yml, and .json"):
        web_diagnostics_services.validate_supported_editor_path("scene.md")

    actions = [
        SyncAction(
            target_name="target-a",
            relative_path="image/prompts/scene.txt",
            action=SyncActionType.CREATE,
            source_path=None,
            target_path=None,
            reason="new file",
        ),
        SyncAction(
            target_name="target-b",
            relative_path="image/prompts/other.txt",
            action=SyncActionType.TARGET_ONLY,
            source_path=None,
            target_path=None,
            reason=None,
        ),
    ]
    plan = SyncPlan(source_root=tmp_path, map_path=tmp_path / "mirror_map.yaml", actions=actions)
    assert web_diagnostics_services.counts_for_plan(plan) == {
        "create": 1,
        "update": 0,
        "unchanged": 0,
        "target_only": 1,
    }
    assert web_diagnostics_services.action_by_target_for_relative_path(
        plan,
        relative_path="image/prompts/scene.txt",
    ) == {"target-a": "create"}
    assert web_diagnostics_services.serialize_action(actions[0]).reason == "new file"

    invalid_utf8_path = tmp_path / "invalid.txt"
    invalid_utf8_path.write_bytes(b"\xff")
    with pytest.raises(ValueError, match="Unable to read text for diff"):
        web_diagnostics_services.read_optional_text(invalid_utf8_path)
    assert web_diagnostics_services.read_optional_text(tmp_path / "missing.txt") is None
    assert (
        web_diagnostics_services.content_signature(
            source_content=None,
            exists=False,
        )
        == "__missing__"
    )
    assert (
        web_diagnostics_services.content_signature(
            source_content=None,
            exists=True,
        )
        == "__unreadable__"
    )

    mud_source = Path("/tmp/pipeworks_mud_server/data/worlds/pipeworks_web/policies")
    assert (
        web_diagnostics_services.canonical_source_label(mud_source)
        == "canonical-source: mud-server"
    )
    generic_source = Path("/tmp/any/other/source")
    assert web_diagnostics_services.canonical_source_label(generic_source).startswith(
        "canonical-source:"
    )

    fake_ipc = SimpleNamespace(
        PolicyHashEntry=lambda *, relative_path, content_hash: SimpleNamespace(
            relative_path=relative_path,
            content_hash=content_hash,
        ),
        compute_policy_file_hash=lambda relative_path, _bytes: f"file::{relative_path}",
        compute_policy_tree_hash=lambda entries: f"tree::{len(entries)}",
    )
    assert (
        web_diagnostics_services.compute_file_hash(
            "image/prompts/scene.txt",
            b"content",
            ipc_hashing_module=fake_ipc,
        )
        == "file::image/prompts/scene.txt"
    )
    assert (
        web_diagnostics_services.compute_tree_hash(
            entries=[
                web_diagnostics_services.PolicyHashEntry(
                    relative_path="image/prompts/scene.txt",
                    content_hash="h1",
                )
            ],
            ipc_hashing_module=fake_ipc,
        )
        == "tree::1"
    )
