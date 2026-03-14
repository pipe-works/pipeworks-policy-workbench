# Policy Workbench Operator Guide (API-Only)

## Purpose

This guide defines the current production-intent workflow for Policy Workbench.

Authority model:

1. Mud-server policy APIs are canonical.
2. Policy Workbench is an API authoring client.

## Scope

In scope:

1. Select mud-server environment (`server_dev` or `server_prod`).
2. Login with admin/superuser credentials.
3. Load policy inventory from mud-server APIs.
4. Edit/save policy variants through canonical APIs.
5. Optionally activate by scope (`world_id`, optional `client_profile`).

Out of scope:

1. Offline mode.
2. Direct local file write authoring.
3. Sync Impact UI workflows.

## Start the Workbench

From repository root:

```bash
pyenv local ppw
pyenv exec pip install -e ".[dev]"
pyenv exec pw-policy serve
```

Open the shown local URL in your browser.

## Select Environment and Login

1. Choose `Development` or `Production` mode in runtime controls.
2. Set server URL for the selected mode.
3. Enter username and password.
4. Click `Login`.
5. Confirm auth badge/status indicates authorized access.

Notes:

1. Policy API operations require `admin` or `superuser`.
2. Session failures should be treated as auth/config errors, not policy-data errors.
3. Type/status filter options are sourced from mud-server policy capabilities.

## Canonical Authoring Flow

1. In Canonical Policy Objects (DB), select `world` first, then choose filters (`type`, `namespace`, `status`) as needed.
2. Click refresh/load inventory.
3. Select one policy object.
4. Confirm Current Object metadata (policy id/type/namespace/key/variant/status/version/hash).
5. Edit policy object content in editor.
6. Save policy.
7. Optionally enable activation and provide `client_profile` before save (world scope is taken from Canonical Policy Objects selection).
8. Confirm save response metadata (policy id, variant, version/hash, validation id).

Contract notes:

1. Save flow is validate first, then upsert, then optional activate.
2. Legacy tree/file endpoints (`GET /api/tree`, `GET|PUT /api/file`) are intentionally disabled (`410`).

Migration mapping:

1. `GET /api/tree` is replaced by `GET /api/policies` for canonical inventory.
2. `GET /api/file` is replaced by `GET /api/policies/{policy_id}` for canonical reads.
3. `PUT /api/file` is replaced by `POST /api/policy-save` for canonical writes.

## Troubleshooting

If inventory is empty:

1. Verify runtime mode URL points at the intended mud-server.
2. Verify login is successful and role is `admin` or `superuser`.
3. Confirm mud-server has imported/created policy objects.

If save fails:

1. Review returned validation detail from save response.
2. Confirm selected policy type/namespace/key/variant is correct.
3. Confirm selected world scope and optional `client_profile` are intentional.
4. Re-check server URL/session and try again.

## Versioning

This guide is authoritative for current Workbench operations and should be
updated whenever runtime behavior changes.
