# pipeworks-policy-workbench

Cross-repo tooling for Pipe-Works policy authoring, validation, and sync.

## Purpose

This repository is the planned single source of truth for policy editing workflows that are currently spread across multiple repos.

Primary goals:
- reduce human error when editing policy files
- reduce app hopping across repositories
- provide repeatable sync and validation flows

## Scope (Initial)

- policy-aware CLI foundation
- policy validation entry points
- mirror/sync orchestration across target repositories
- handover and working docs in `_working/`

## Environment

This repo uses `pyenv`.

```bash
pyenv local ppw
pyenv exec pip install -e ".[dev]"
```

## Commands

```bash
pyenv exec pytest -q
pyenv exec ruff check src tests
pyenv exec black --check src tests
pyenv exec mypy src
pyenv exec pw-policy --help
pyenv exec pw-policy doctor
pyenv exec pw-policy validate
pyenv exec pw-policy sync
pyenv exec pw-policy sync --format json
pyenv exec pw-policy sync --apply --yes
pyenv exec pw-policy serve
```

CLI behavior highlights:
- `pw-policy doctor` scans the canonical policy tree, prints role counts and validation summary, and exits non-zero on error-level validation failures
- `pw-policy validate` prints deterministic issue lines and summary, returning non-zero when errors exist
- both `doctor` and `validate` accept `--root` to validate alternate fixture trees
- `pw-policy sync` defaults to dry-run planning and uses `config/mirror_map.yaml` as mapping contract
- `pw-policy sync --format json` emits machine-readable action payloads for automation
- `pw-policy sync --apply --yes` applies create/update actions only and leaves target-only files untouched by default

`pw-policy serve` behavior:
- binds to the first unused port in `8000-8099`
- supports `--port` as a preferred in-range port and falls back within range if occupied
- prefixes server log lines with `pol-work-bench` for easier pane identification

Phase 2 web authoring behavior:
- workbench runtime saves now go through mud-server policy APIs (`validate -> save -> optional activate`)
- direct filesystem writes through `PUT /api/file` are disabled by design
- current authoring pilot mapping is `species_block` (`image/blocks/species/*_v*.yaml`)
- center panel now includes API-first policy inventory filters/selectors (`policy_type`, `namespace`, `status`)
- center panel includes activation scope controls (`world_id`, optional `client_profile`) for save+activate flow
- inventory-backed object loading uses:
  - `GET /api/policies`
  - `GET /api/policies/{policy_id}`
  - `GET /api/policy-activations-live`
  - `GET /api/policy-publish-runs/{publish_run_id}`
- configure mud-server connectivity with:
  - `PW_POLICY_MUD_API_BASE_URL` (default: `http://127.0.0.1:8000`)
  - `PW_POLICY_MUD_SESSION_ID` (required unless provided in request payload)
  - session must belong to an `admin` or `superuser` account for server-backed policy operations

## Current Layout

- `src/policy_workbench/` - Python package and CLI entrypoint
- `src/policy_workbench/commands/` - command handlers (`doctor`, `validate`, `sync`)
- `config/mirror_map.yaml` - explicit source/target mapping contract used by sync planning
- `tests/` - unit/integration tests
- `_working/` - live design notes and handover docs
- `_working/shared` - symlink to shared working directory used across repos

## License

GPL-3.0-or-later (see `LICENSE`).
