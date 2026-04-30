# Deploy

The repo ships checked-in deploy templates for the Luminal host layout.

## Service shape

| Surface | Value |
| --- | --- |
| Live hostname | `https://policies.pipeworks.luminal.local/` |
| Backend bind | `127.0.0.1:8040` |
| Service unit | `pipeworks-policy-workbench.service` |
| Host env file | `/etc/pipeworks/policy-workbench/policy-workbench.env` |
| Workspace venv | `/srv/work/pipeworks/venvs/pw-policy-workbench` |

## Templates

- `deploy/systemd/pipeworks-policy-workbench.service`
- `deploy/nginx/policies.pipeworks.luminal.local`
- `deploy/etc/pipeworks/policy-workbench/policy-workbench.env.example`

These are checked-in templates — machine-specific rollout state lives outside
the repo.

## Local run posture

For local development, `pw-policy serve` binds `127.0.0.1` by default and
chooses an available port in `8000-8099` (respecting `PW_POLICY_DEFAULT_PORT`
when set). `--host 0.0.0.0` is supported for explicit ad hoc exposure but is
not the normal Luminal service posture.
