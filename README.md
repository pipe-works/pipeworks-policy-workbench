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
```

## Current Layout

- `src/policy_workbench/` - Python package and CLI entrypoint
- `tests/` - unit/integration tests
- `_working/` - live design notes and handover docs
- `_working/shared` - symlink to shared working directory used across repos

## License

GPL-3.0-or-later (see `LICENSE`).
