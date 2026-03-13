# pipeworks-policy-workbench

API-first authoring client for mud-server canonical policy APIs.

## Purpose

Policy Workbench exists to reduce policy-editing mistakes by making mud-server
policy objects the primary authoring surface.

Primary goals:
- reduce human error when editing policy content
- keep authoring aligned with mud-server API contracts
- keep local mirror diagnostics optional and non-authoritative

Current operator workflow is documented in:

- [`docs/OPERATOR_GUIDE_API_ONLY.md`](docs/OPERATOR_GUIDE_API_ONLY.md)

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
pyenv exec pw-policy serve
```

Optional local mirror diagnostics (non-authoritative):

```bash
pyenv exec pw-policy doctor
pyenv exec pw-policy validate
pyenv exec pw-policy sync
pyenv exec pw-policy sync --format json
pyenv exec pw-policy sync --apply --yes
```

`pw-policy serve` behavior:
- binds to the first unused port in `8000-8099`
- supports `--port` as a preferred in-range port and falls back within range if occupied
- prefixes server log lines with `pol-work-bench` for easier pane identification

API-only authoring behavior:
- runtime modes are `server_dev` and `server_prod` only
- mud-server login is required; policy APIs are admin/superuser only
- saves use mud-server policy APIs (`validate -> save -> optional activate`)
- direct file writes (`PUT /api/file`) are disabled (`410`)
- legacy request query overrides (`root`, `map_path`) are rejected (`400`)

## Current Layout

- `src/policy_workbench/` - Python package and CLI entrypoint
- `src/policy_workbench/commands/` - command handlers (`doctor`, `validate`, `sync`, `serve`)
- `docs/OPERATOR_GUIDE_API_ONLY.md` - current canonical operator guide
- `config/mirror_map.yaml` - local mirror diagnostics contract (non-authoritative)
- `tests/` - unit/integration tests
- `_working/` - live design notes and handover docs
- `_working/shared` - symlink to shared working directory used across repos

## License

GPL-3.0-or-later (see `LICENSE`).
