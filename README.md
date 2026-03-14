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
- legacy tree/file endpoints (`GET /api/tree`, `GET|PUT /api/file`) are disabled (`410`)
- legacy request query overrides (`root`, `map_path`) are rejected (`400`)
- `/api/validate` is explicitly local mirror diagnostics and returns canonical authority labels

Migration guidance:
- replace legacy tree/file endpoint usage with canonical API object workflows:
  - `GET /api/tree` -> `GET /api/policies`
  - `GET /api/file` -> `GET /api/policies/{policy_id}`
  - `PUT /api/file` -> `POST /api/policy-save`
- treat `/api/validate` as local mirror diagnostics only; canonical correctness remains mud-server API validation/save/activation behavior

Developer hardening checks:
- run focused transport/proxy/source diagnostics coverage for refactored modules:
  - `pyenv exec pytest -q --cov=policy_workbench.mud_api_client --cov=policy_workbench.web_policy_proxy_services --cov=policy_workbench.web_source_services --cov=policy_workbench.web_diagnostics_services --cov-report=term-missing`

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
