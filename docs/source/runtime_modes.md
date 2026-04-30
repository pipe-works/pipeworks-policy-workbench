# Runtime Modes

The workbench is mud-server API first. Two source-mode profiles ship by
default:

- `server_dev` — dev mud-server profile
- `server_prod` — production mud-server profile

Both modes resolve to explicit HTTP(S) mud-server base URLs. URL defaults
come from environment variables, then in-memory overrides set through the
UI's runtime-mode controls.

## Canonical environment variables

| Variable | Purpose |
| --- | --- |
| `PW_POLICY_SOURCE_MODE` | Active profile (`server_dev` / `server_prod`) |
| `PW_POLICY_DEV_MUD_API_BASE_URL` | Default URL for `server_dev` |
| `PW_POLICY_PROD_MUD_API_BASE_URL` | Default URL for `server_prod` |
| `PW_POLICY_CANONICAL_ROOT` | Canonical policy root for CLI validation |
| `PW_POLICY_DEFAULT_PORT` | Preferred port for `pw-policy serve` |

The following companion variables are accepted as fallbacks by
`runtime_mode.py`:
`PW_POLICY_MUD_API_BASE_URL`, `PW_POLICY_LOCAL_MUD_API_BASE_URL`,
`PW_POLICY_REMOTE_DEV_MUD_API_BASE_URL`,
`PW_POLICY_REMOTE_PROD_MUD_API_BASE_URL`.

## Browser sessions

After login, the web app stores a server-side session binding and issues a
hardened HttpOnly cookie (`pw_policy_runtime_session`) so the runtime session
survives page refreshes for up to 12 hours.

When mud-server invalidates a session before that cookie expires, the next
proxied request returns a 401. The backend pops the cached session record and
attaches a `Set-Cookie` clear header to the 401 response; the frontend
reacts by flipping local auth state to `unauthenticated` so the UI prompts
re-login on the same click that hit the dead session.

## HTTP status semantics

The web routes deliberately preserve coarse mud-server categories so the UI
can disambiguate states cleanly:

- **401** — session is missing/invalid/expired (`Invalid or expired session`,
  `Invalid session user`)
- **403** — session is valid but the role is not admin/superuser
- **400** — other request errors
- **503** — runtime mode does not provide a server URL
