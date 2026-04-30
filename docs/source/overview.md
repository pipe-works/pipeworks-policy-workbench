# Overview

The workbench has three surfaces:

1. **CLI** — `pw-policy` with `doctor`, `validate`, and `serve` subcommands.
2. **Web app** — FastAPI single-page workbench for interactive policy
   authoring against mud-server APIs.
3. **Deploy templates** — checked-in Luminal systemd/nginx examples under
   `deploy/`.

## Codebase shape

The package layout under `src/policy_workbench/`:

- `cli.py` — thin argument parser and dispatch
- `commands/` — `doctor.py`, `validate.py` command implementations
- `server.py` — Uvicorn startup, port selection, log configuration
- `web_app.py` — FastAPI factory, HTML routes, API routes, browser session
  cookie handling
- `runtime_mode.py` — `server_dev` / `server_prod` profile selection and URL
  override handling
- `policy_authoring.py` — save/validate authoring helpers and runtime config
  resolution
- `mud_api_client.py`, `mud_api_runtime.py` — mud-server authentication and
  policy API interactions
- `web_*_services.py` — concern-split web-route helpers (diagnostics,
  runtime, source, policy proxy, local metadata)
- `tree_model.py`, `validators.py`, `extractors.py`, `models.py` — local
  policy tree scanning and validation support
- `pathing.py` — canonical root and path resolution
- `env_loader.py` — lightweight `.env` loader

## Frontend

The workbench frontend is plain HTML/CSS/JS — no bundler, no build step.
Source lives under `src/policy_workbench/static/` with the bulk in
`static/workbench/` (composition root + ES modules, including the
`inventory/` subtree).
