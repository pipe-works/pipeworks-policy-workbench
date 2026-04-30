# Pipeworks Policy Workbench

Local authoring and operations surface for canonical policy work against
mud-server APIs. The workbench ships a `pw-policy` CLI and a FastAPI web app
that talks to the canonical mud-server policy API for inventory, validation,
and save/activate flows.

This documentation set is the entry point for users and contributors. For
shorter day-to-day notes, see the project [README](https://github.com/pipe-works/pipeworks-policy-workbench/blob/main/README.md)
and the agent-facing [AGENTS.md](https://github.com/pipe-works/pipeworks-policy-workbench/blob/main/AGENTS.md).

```{toctree}
:maxdepth: 2
:caption: Contents

overview
runtime_modes
deploy
api/index
```

## Quick Start

```bash
VENV=/srv/work/pipeworks/venvs/pw-policy-workbench

python3.12 -m venv "$VENV"
"$VENV/bin/pip" install -e ".[dev,docs]"
cp .example.env .env

"$VENV/bin/pw-policy" doctor
"$VENV/bin/pw-policy" validate
"$VENV/bin/pw-policy" serve
```

`serve` binds `127.0.0.1` and chooses an available port in `8000-8099`
(respecting `PW_POLICY_DEFAULT_PORT`). Open the printed URL to reach the
workbench UI.
