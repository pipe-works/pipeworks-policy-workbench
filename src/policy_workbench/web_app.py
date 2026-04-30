"""FastAPI application factory for the Phase 3 policy workbench UI."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from secrets import token_urlsafe
from threading import RLock
from typing import NoReturn, TypeVar

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __version__
from .policy_authoring import (
    PolicySelector,
    resolve_runtime_config,
    save_policy_variant_from_raw_content,
    validate_policy_variant_from_raw_content,
)
from .runtime_mode import (
    RuntimeModeUnavailableError,
    get_runtime_mode,
    require_server_api_url,
    set_runtime_mode,
)
from .web_models import (
    PolicyActivationScopeResponse,
    PolicyActivationSetRequest,
    PolicyActivationSetResponse,
    PolicyInventoryResponse,
    PolicyObjectDetailResponse,
    PolicyPublishRunProxyResponse,
    PolicySaveRequest,
    PolicySaveResponse,
    PolicyTypeOptionsResponse,
    PolicyValidateRequest,
    PolicyValidateResponse,
    RuntimeAuthResponse,
    RuntimeLoginRequest,
    RuntimeLoginResponse,
    RuntimeLogoutResponse,
    RuntimeModeOptionResponse,
    RuntimeModeRequest,
    RuntimeModeResponse,
)
from .web_services import (
    build_policy_activation_scope_payload,
    build_policy_activation_set_payload,
    build_policy_inventory_payload,
    build_policy_namespace_options_payload,
    build_policy_object_detail_payload,
    build_policy_publish_run_payload,
    build_policy_status_options_payload,
    build_policy_type_options_payload,
    build_runtime_auth_payload,
    build_runtime_login_payload,
)

_HERE = Path(__file__).resolve().parent
_TEMPLATES_DIR = _HERE / "templates"
_STATIC_DIR = _HERE / "static"
_ResponseT = TypeVar("_ResponseT")
_RUNTIME_SESSION_COOKIE_NAME = "pw_policy_runtime_session"
_RUNTIME_SESSION_MAX_AGE_SECONDS = 12 * 60 * 60


@dataclass(slots=True)
class _RuntimeBrowserSession:
    """Server-side runtime session binding for browser refresh persistence."""

    session_id: str
    mode_key: str
    server_url: str
    available_worlds: list[dict[str, object]]
    created_at_epoch: int
    updated_at_epoch: int


def create_web_app(
    *,
    source_root_override: str | None = None,
) -> FastAPI:
    """Create configured FastAPI app instance for UI and API routes."""

    app = FastAPI(title="Pipeworks Policy Workbench", version=__version__)

    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
    runtime_browser_sessions: dict[str, _RuntimeBrowserSession] = {}
    runtime_browser_sessions_lock = RLock()

    def _normalize_server_url_for_binding(value: str | None) -> str:
        """Normalize runtime server URLs for stable session binding comparisons."""
        return str(value or "").strip().rstrip("/")

    def _sanitize_available_worlds(
        world_rows: list[dict[str, object]] | None,
    ) -> list[dict[str, object]]:
        """Retain only stable world row dictionaries with non-empty IDs."""
        if not isinstance(world_rows, list):
            return []
        sanitized: list[dict[str, object]] = []
        for row in world_rows:
            if not isinstance(row, dict):
                continue
            world_id = str(row.get("id") or "").strip()
            if not world_id:
                continue
            normalized_row = dict(row)
            normalized_row["id"] = world_id
            world_name = str(row.get("name") or "").strip()
            if world_name:
                normalized_row["name"] = world_name
            sanitized.append(normalized_row)
        return sanitized

    def _runtime_cookie_secure(request: Request) -> bool:
        """Return whether runtime session cookie should use the Secure attribute."""
        if request.url.scheme == "https":
            return True
        hostname = str(request.url.hostname or "").strip().lower()
        return hostname not in {"localhost", "127.0.0.1", "::1"}

    def _set_runtime_session_cookie(response: Response, *, request: Request, token: str) -> None:
        """Set hardened browser cookie for one runtime browser-session token."""
        response.set_cookie(
            key=_RUNTIME_SESSION_COOKIE_NAME,
            value=token,
            max_age=_RUNTIME_SESSION_MAX_AGE_SECONDS,
            httponly=True,
            secure=_runtime_cookie_secure(request),
            samesite="strict",
            path="/",
        )

    def _clear_runtime_session_cookie(response: Response, *, request: Request) -> None:
        """Delete runtime browser-session cookie from browser storage."""
        response.delete_cookie(
            key=_RUNTIME_SESSION_COOKIE_NAME,
            httponly=True,
            secure=_runtime_cookie_secure(request),
            samesite="strict",
            path="/",
        )

    def _purge_expired_runtime_browser_sessions(*, now_epoch: int | None = None) -> None:
        """Evict expired runtime browser-session records from in-memory store."""
        now = int(now_epoch if now_epoch is not None else time.time())
        with runtime_browser_sessions_lock:
            expired_tokens = [
                token
                for token, record in runtime_browser_sessions.items()
                if now - record.updated_at_epoch >= _RUNTIME_SESSION_MAX_AGE_SECONDS
            ]
            for token in expired_tokens:
                runtime_browser_sessions.pop(token, None)

    def _store_runtime_browser_session(
        *,
        mode_key: str,
        server_url: str | None,
        session_id: str,
        available_worlds: list[dict[str, object]] | None,
    ) -> str:
        """Create one runtime browser-session record and return opaque token."""
        now = int(time.time())
        token = token_urlsafe(32)
        record = _RuntimeBrowserSession(
            session_id=session_id,
            mode_key=mode_key,
            server_url=_normalize_server_url_for_binding(server_url),
            available_worlds=_sanitize_available_worlds(available_worlds),
            created_at_epoch=now,
            updated_at_epoch=now,
        )
        with runtime_browser_sessions_lock:
            runtime_browser_sessions[token] = record
        _purge_expired_runtime_browser_sessions(now_epoch=now)
        return token

    def _pop_runtime_browser_session_by_token(token: str | None) -> _RuntimeBrowserSession | None:
        """Remove one runtime browser-session record by token and return it."""
        normalized_token = str(token or "").strip()
        if not normalized_token:
            return None
        with runtime_browser_sessions_lock:
            return runtime_browser_sessions.pop(normalized_token, None)

    def _resolve_runtime_browser_session(
        *,
        request: Request,
        mode_key: str,
        server_url: str | None,
    ) -> tuple[str | None, list[dict[str, object]], str | None]:
        """Resolve runtime browser-session for request cookie and active mode/url."""
        _purge_expired_runtime_browser_sessions()
        token = str(request.cookies.get(_RUNTIME_SESSION_COOKIE_NAME, "")).strip()
        if not token:
            return (None, [], None)
        with runtime_browser_sessions_lock:
            record = runtime_browser_sessions.get(token)
            if record is None:
                return (None, [], token)
            if (
                record.mode_key != mode_key
                or record.server_url != _normalize_server_url_for_binding(server_url)
            ):
                runtime_browser_sessions.pop(token, None)
                return (None, [], token)
            record.updated_at_epoch = int(time.time())
            return (
                record.session_id,
                [dict(row) for row in record.available_worlds],
                token,
            )

    def _status_code_for_mud_api_error(detail: str) -> int:
        """Map mud-server auth/permission failures to stable HTTP status codes."""
        # Keep this mapping string-based and conservative so route behavior
        # stays stable even if mud-server evolves internal exception classes.
        # The workbench depends on these coarse categories for clear UX states:
        # unauthenticated (401), forbidden role (403), other request errors (400).
        if (
            "Policy API requires admin or superuser role." in detail
            or "role is not admin/superuser" in detail
        ):
            return 403
        if "Invalid or expired session" in detail or "Invalid session user" in detail:
            return 401
        return 400

    @dataclass(slots=True)
    class _AuthSessionContext:
        """Bundle request/response/cookie token for per-request session cleanup."""

        request: Request
        response: Response
        cookie_token: str | None

    def _build_clear_runtime_session_cookie_header(*, request: Request) -> str:
        """Return a Set-Cookie header value that clears the runtime session cookie.

        Using a header attached to the HTTPException is the only reliable way to
        deliver cookie state changes alongside an error response — FastAPI's
        default exception handler discards mutations made to the injected
        ``Response`` object.
        """
        helper = Response()
        helper.delete_cookie(
            key=_RUNTIME_SESSION_COOKIE_NAME,
            httponly=True,
            secure=_runtime_cookie_secure(request),
            samesite="strict",
            path="/",
        )
        for header_name, header_value in helper.raw_headers:
            if header_name.lower() == b"set-cookie":
                return header_value.decode("latin-1")
        return ""

    def _invalidate_runtime_session_on_auth_failure(
        *,
        detail: str,
        auth_ctx: _AuthSessionContext | None,
    ) -> dict[str, str] | None:
        """Drop cached browser-session record when mud-server reports auth failure.

        Without this the workbench keeps forwarding a session_id that mud-server
        has already invalidated, so every subsequent click repeats the same 401
        and the auth badge stays stuck on a stale "authorized" reading.
        """
        if auth_ctx is None:
            return None
        if _status_code_for_mud_api_error(detail) != 401:
            return None
        if auth_ctx.cookie_token:
            _pop_runtime_browser_session_by_token(auth_ctx.cookie_token)
        clear_header = _build_clear_runtime_session_cookie_header(request=auth_ctx.request)
        return {"set-cookie": clear_header} if clear_header else None

    def _raise_mud_service_http_error(
        exc: ValueError | OSError,
        *,
        auth_ctx: _AuthSessionContext | None = None,
    ) -> NoReturn:
        """Raise one normalized HTTPException for mud-service failures."""

        detail = str(exc)
        cleanup_headers = _invalidate_runtime_session_on_auth_failure(
            detail=detail, auth_ctx=auth_ctx
        )
        raise HTTPException(
            status_code=_status_code_for_mud_api_error(detail),
            detail=detail,
            headers=cleanup_headers,
        ) from exc

    def _run_mud_service(
        call: Callable[[], _ResponseT],
        *,
        auth_ctx: _AuthSessionContext | None = None,
    ) -> _ResponseT:
        """Execute one mud-service call and normalize ValueError/OSError mapping."""

        try:
            return call()
        except (ValueError, OSError) as exc:
            _raise_mud_service_http_error(exc, auth_ctx=auth_ctx)

    def _run_server_api_route(
        call: Callable[[str], _ResponseT],
        *,
        auth_ctx: _AuthSessionContext | None = None,
    ) -> _ResponseT:
        """Resolve active server URL and execute one mud-server-backed route action."""

        try:
            server_api_url = require_server_api_url()
            return _run_mud_service(lambda: call(server_api_url), auth_ctx=auth_ctx)
        except RuntimeModeUnavailableError as exc:
            # Fail closed when runtime mode does not provide a server URL.
            # Returning 503 keeps callers from mistaking environment/runtime
            # misconfiguration for policy validation/data problems.
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    def _build_runtime_mode_response() -> RuntimeModeResponse:
        """Return runtime mode payload serialized to API response models."""
        state = get_runtime_mode()
        return RuntimeModeResponse(
            mode_key=state.mode_key,
            source_kind=state.source_kind,
            active_server_url=state.active_server_url,
            options=[
                RuntimeModeOptionResponse(
                    mode_key=option.mode_key,
                    label=option.label,
                    source_kind=option.source_kind,
                    default_server_url=option.default_server_url,
                    active_server_url=(
                        state.active_server_url if option.mode_key == state.mode_key else None
                    ),
                    url_editable=option.url_editable,
                )
                for option in state.options
            ],
        )

    def _resolve_request_session_id(
        *,
        request: Request,
        mode_key: str,
        server_url: str | None,
        explicit_session_id: str | None,
    ) -> tuple[str | None, list[dict[str, object]], str | None]:
        """Resolve runtime session from explicit value first, then secure browser cookie."""
        normalized_explicit = str(explicit_session_id or "").strip()
        if normalized_explicit:
            return (normalized_explicit, [], None)
        return _resolve_runtime_browser_session(
            request=request,
            mode_key=mode_key,
            server_url=server_url,
        )

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        """Render the single-page policy workbench shell."""

        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"app_version": __version__},
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Simple readiness endpoint for local runtime checks."""

        return {"status": "ok"}

    @app.get("/api/runtime-mode", response_model=RuntimeModeResponse)
    async def api_runtime_mode() -> RuntimeModeResponse:
        """Return active source mode and available workbench mode profiles."""
        return _build_runtime_mode_response()

    @app.post("/api/runtime-mode", response_model=RuntimeModeResponse)
    async def api_runtime_mode_set(payload: RuntimeModeRequest) -> RuntimeModeResponse:
        """Switch active source mode and optional mud-server URL override."""
        try:
            set_runtime_mode(mode_key=payload.mode_key, server_url=payload.server_url)
            return _build_runtime_mode_response()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/runtime-auth", response_model=RuntimeAuthResponse)
    async def api_runtime_auth(
        request: Request,
        response: Response,
        session_id: str | None = Query(default=None),
    ) -> RuntimeAuthResponse:
        """Return explicit runtime auth/access status for server-backed operations."""
        state = get_runtime_mode()
        resolved_session_id, cookie_worlds, cookie_token = _resolve_request_session_id(
            request=request,
            mode_key=state.mode_key,
            server_url=state.active_server_url,
            explicit_session_id=session_id,
        )
        payload = build_runtime_auth_payload(
            mode_key=state.mode_key,
            source_kind=state.source_kind,
            active_server_url=state.active_server_url,
            session_id_override=resolved_session_id,
            base_url_override=state.active_server_url,
        )
        if cookie_token and payload.status in {"missing_session", "unauthenticated"}:
            _pop_runtime_browser_session_by_token(cookie_token)
            _clear_runtime_session_cookie(response, request=request)
        if payload.access_granted and cookie_worlds:
            payload = payload.model_copy(update={"available_worlds": cookie_worlds})
        return payload

    @app.post("/api/runtime-login", response_model=RuntimeLoginResponse)
    async def api_runtime_login(
        payload: RuntimeLoginRequest,
        request: Request,
        response: Response,
    ) -> RuntimeLoginResponse:
        """Authenticate to active mud-server profile and return session bootstrap data."""
        state = get_runtime_mode()
        service_payload = _run_mud_service(
            lambda: build_runtime_login_payload(
                mode_key=state.mode_key,
                source_kind=state.source_kind,
                active_server_url=state.active_server_url,
                username=payload.username,
                password=payload.password,
                base_url_override=state.active_server_url,
            )
        )
        normalized_worlds = _sanitize_available_worlds(service_payload.available_worlds)
        if service_payload.success and service_payload.session_id:
            token = _store_runtime_browser_session(
                mode_key=state.mode_key,
                server_url=state.active_server_url,
                session_id=service_payload.session_id,
                available_worlds=normalized_worlds,
            )
            _set_runtime_session_cookie(response, request=request, token=token)
        else:
            stale_token = str(request.cookies.get(_RUNTIME_SESSION_COOKIE_NAME, "")).strip()
            if stale_token:
                _pop_runtime_browser_session_by_token(stale_token)
            _clear_runtime_session_cookie(response, request=request)
        return RuntimeLoginResponse(
            success=service_payload.success,
            session_id=None,
            role=service_payload.role,
            available_worlds=normalized_worlds,
            detail=service_payload.detail,
        )

    @app.post("/api/runtime-logout", response_model=RuntimeLogoutResponse)
    async def api_runtime_logout(request: Request, response: Response) -> RuntimeLogoutResponse:
        """Clear active browser-bound runtime session token."""
        session_token = str(request.cookies.get(_RUNTIME_SESSION_COOKIE_NAME, "")).strip()
        if session_token:
            _pop_runtime_browser_session_by_token(session_token)
        _clear_runtime_session_cookie(response, request=request)
        return RuntimeLogoutResponse(success=True, detail="Runtime session cleared.")

    @app.get("/api/policy-types", response_model=PolicyTypeOptionsResponse)
    async def api_policy_types(
        request: Request,
        response: Response,
        session_id: str | None = Query(default=None),
    ) -> PolicyTypeOptionsResponse:
        """Return canonical policy-type options for inventory filtering."""
        state = get_runtime_mode()
        resolved_session_id, _, cookie_token = _resolve_request_session_id(
            request=request,
            mode_key=state.mode_key,
            server_url=state.active_server_url,
            explicit_session_id=session_id,
        )
        auth_ctx = _AuthSessionContext(
            request=request, response=response, cookie_token=cookie_token
        )
        return _run_mud_service(
            lambda: build_policy_type_options_payload(
                source_kind=state.source_kind,
                active_server_url=state.active_server_url,
                session_id_override=resolved_session_id,
                base_url_override=state.active_server_url,
            ),
            auth_ctx=auth_ctx,
        )

    @app.get("/api/policy-namespaces", response_model=PolicyTypeOptionsResponse)
    async def api_policy_namespaces(
        request: Request,
        response: Response,
        policy_type: str | None = Query(default=None),
        session_id: str | None = Query(default=None),
    ) -> PolicyTypeOptionsResponse:
        """Return canonical policy namespace options for inventory filtering."""
        state = get_runtime_mode()
        resolved_session_id, _, cookie_token = _resolve_request_session_id(
            request=request,
            mode_key=state.mode_key,
            server_url=state.active_server_url,
            explicit_session_id=session_id,
        )
        auth_ctx = _AuthSessionContext(
            request=request, response=response, cookie_token=cookie_token
        )
        return _run_mud_service(
            lambda: build_policy_namespace_options_payload(
                source_kind=state.source_kind,
                active_server_url=state.active_server_url,
                session_id_override=resolved_session_id,
                policy_type=policy_type,
                base_url_override=state.active_server_url,
            ),
            auth_ctx=auth_ctx,
        )

    @app.get("/api/policy-statuses", response_model=PolicyTypeOptionsResponse)
    async def api_policy_statuses(
        request: Request,
        response: Response,
        session_id: str | None = Query(default=None),
    ) -> PolicyTypeOptionsResponse:
        """Return canonical policy status options for inventory filtering."""
        state = get_runtime_mode()
        resolved_session_id, _, cookie_token = _resolve_request_session_id(
            request=request,
            mode_key=state.mode_key,
            server_url=state.active_server_url,
            explicit_session_id=session_id,
        )
        auth_ctx = _AuthSessionContext(
            request=request, response=response, cookie_token=cookie_token
        )
        return _run_mud_service(
            lambda: build_policy_status_options_payload(
                source_kind=state.source_kind,
                active_server_url=state.active_server_url,
                session_id_override=resolved_session_id,
                base_url_override=state.active_server_url,
            ),
            auth_ctx=auth_ctx,
        )

    @app.get("/api/policies", response_model=PolicyInventoryResponse)
    async def api_policies(
        request: Request,
        response: Response,
        policy_type: str | None = Query(default=None),
        namespace: str | None = Query(default=None),
        status: str | None = Query(default=None),
        session_id: str | None = Query(default=None),
    ) -> PolicyInventoryResponse:
        """Return API-first policy inventory list from mud-server canonical API."""

        state = get_runtime_mode()
        resolved_session_id, _, cookie_token = _resolve_request_session_id(
            request=request,
            mode_key=state.mode_key,
            server_url=state.active_server_url,
            explicit_session_id=session_id,
        )
        auth_ctx = _AuthSessionContext(
            request=request, response=response, cookie_token=cookie_token
        )
        return _run_server_api_route(
            lambda server_api_url: build_policy_inventory_payload(
                policy_type=policy_type,
                namespace=namespace,
                status=status,
                session_id_override=resolved_session_id,
                base_url_override=server_api_url,
            ),
            auth_ctx=auth_ctx,
        )

    @app.get("/api/policies/{policy_id}", response_model=PolicyObjectDetailResponse)
    async def api_policy_detail(
        request: Request,
        response: Response,
        policy_id: str,
        variant: str | None = Query(default=None),
        session_id: str | None = Query(default=None),
    ) -> PolicyObjectDetailResponse:
        """Return one policy object detail payload from mud-server canonical API."""

        state = get_runtime_mode()
        resolved_session_id, _, cookie_token = _resolve_request_session_id(
            request=request,
            mode_key=state.mode_key,
            server_url=state.active_server_url,
            explicit_session_id=session_id,
        )
        auth_ctx = _AuthSessionContext(
            request=request, response=response, cookie_token=cookie_token
        )
        return _run_server_api_route(
            lambda server_api_url: build_policy_object_detail_payload(
                policy_id=policy_id,
                variant=variant,
                session_id_override=resolved_session_id,
                base_url_override=server_api_url,
            ),
            auth_ctx=auth_ctx,
        )

    @app.get("/api/policy-activations-live", response_model=PolicyActivationScopeResponse)
    async def api_policy_activations_live(
        request: Request,
        response: Response,
        scope: str = Query(min_length=1),
        effective: bool = Query(default=True),
        session_id: str | None = Query(default=None),
    ) -> PolicyActivationScopeResponse:
        """Return scoped activation mappings from mud-server canonical API."""

        state = get_runtime_mode()
        resolved_session_id, _, cookie_token = _resolve_request_session_id(
            request=request,
            mode_key=state.mode_key,
            server_url=state.active_server_url,
            explicit_session_id=session_id,
        )
        auth_ctx = _AuthSessionContext(
            request=request, response=response, cookie_token=cookie_token
        )
        return _run_server_api_route(
            lambda server_api_url: build_policy_activation_scope_payload(
                scope=scope,
                effective=effective,
                session_id_override=resolved_session_id,
                base_url_override=server_api_url,
            ),
            auth_ctx=auth_ctx,
        )

    @app.post("/api/policy-activation-set", response_model=PolicyActivationSetResponse)
    async def api_policy_activation_set(
        request: Request,
        response: Response,
        payload: PolicyActivationSetRequest,
    ) -> PolicyActivationSetResponse:
        """Set one activation pointer through mud-server canonical policy activation API."""
        state = get_runtime_mode()
        resolved_session_id, _, cookie_token = _resolve_request_session_id(
            request=request,
            mode_key=state.mode_key,
            server_url=state.active_server_url,
            explicit_session_id=payload.session_id,
        )
        auth_ctx = _AuthSessionContext(
            request=request, response=response, cookie_token=cookie_token
        )
        return _run_server_api_route(
            lambda server_api_url: build_policy_activation_set_payload(
                world_id=payload.world_id,
                client_profile=payload.client_profile,
                policy_id=payload.policy_id,
                variant=payload.variant,
                activated_by=payload.activated_by,
                session_id_override=resolved_session_id,
                base_url_override=server_api_url,
            ),
            auth_ctx=auth_ctx,
        )

    @app.get(
        "/api/policy-publish-runs/{publish_run_id}",
        response_model=PolicyPublishRunProxyResponse,
    )
    async def api_policy_publish_run(
        request: Request,
        response: Response,
        publish_run_id: int,
        session_id: str | None = Query(default=None),
    ) -> PolicyPublishRunProxyResponse:
        """Return one publish run payload from mud-server canonical publish API."""
        state = get_runtime_mode()
        resolved_session_id, _, cookie_token = _resolve_request_session_id(
            request=request,
            mode_key=state.mode_key,
            server_url=state.active_server_url,
            explicit_session_id=session_id,
        )
        auth_ctx = _AuthSessionContext(
            request=request, response=response, cookie_token=cookie_token
        )
        return _run_server_api_route(
            lambda server_api_url: build_policy_publish_run_payload(
                publish_run_id=publish_run_id,
                session_id_override=resolved_session_id,
                base_url_override=server_api_url,
            ),
            auth_ctx=auth_ctx,
        )

    @app.get("/api/tree")
    async def api_tree():
        """Legacy endpoint removed from API-first surface and fails closed."""

        raise HTTPException(
            status_code=410,
            detail=(
                "Legacy tree endpoint is disabled. Use /api/policies and "
                "/api/policies/{policy_id} for canonical object workflows."
            ),
        )

    @app.get("/api/file")
    async def api_file_read():
        """Legacy endpoint removed from API-first surface and fails closed."""

        raise HTTPException(
            status_code=410,
            detail=(
                "Legacy file endpoint is disabled. Use /api/policies/{policy_id} "
                "for reads and /api/policy-save for writes."
            ),
        )

    @app.put("/api/file")
    async def api_file_write():
        """Legacy endpoint removed from API-first surface and fails closed."""

        raise HTTPException(
            status_code=410,
            detail=(
                "Legacy file endpoint is disabled. Use /api/policy-save for writes "
                "and /api/policies/{policy_id} for canonical reads."
            ),
        )

    @app.post("/api/policy-validate", response_model=PolicyValidateResponse)
    async def api_policy_validate(
        request: Request,
        response: Response,
        payload: PolicyValidateRequest,
    ) -> PolicyValidateResponse:
        """Validate one authorable policy object without writing/upserting it."""

        selector = PolicySelector(
            policy_type=payload.policy_type,
            namespace=payload.namespace,
            policy_key=payload.policy_key,
            variant=payload.variant,
        )
        state = get_runtime_mode()
        resolved_session_id, _, cookie_token = _resolve_request_session_id(
            request=request,
            mode_key=state.mode_key,
            server_url=state.active_server_url,
            explicit_session_id=payload.session_id,
        )
        auth_ctx = _AuthSessionContext(
            request=request, response=response, cookie_token=cookie_token
        )

        def _build_validate_response(server_api_url: str) -> PolicyValidateResponse:
            runtime_config = resolve_runtime_config(
                session_id_override=resolved_session_id,
                base_url_override=server_api_url,
            )
            result = validate_policy_variant_from_raw_content(
                selector=selector,
                raw_content=payload.raw_content,
                schema_version=payload.schema_version,
                status=payload.status,
                actor=payload.actor,
                runtime_config=runtime_config,
            )
            return PolicyValidateResponse(
                policy_id=result.policy_id,
                variant=result.variant,
                policy_version=result.policy_version,
                validation_run_id=result.validation_run_id,
                is_valid=True,
            )

        return _run_server_api_route(_build_validate_response, auth_ctx=auth_ctx)

    @app.post("/api/policy-save", response_model=PolicySaveResponse)
    async def api_policy_save(
        request: Request,
        response: Response,
        payload: PolicySaveRequest,
    ) -> PolicySaveResponse:
        """Save one authorable policy object through mud-server APIs.

        Flow:
        1. Resolve runtime mud-server API config/session.
        2. Validate candidate payload.
        3. Upsert variant.
        4. Optionally activate for a provided scope.
        """

        selector = PolicySelector(
            policy_type=payload.policy_type,
            namespace=payload.namespace,
            policy_key=payload.policy_key,
            variant=payload.variant,
        )
        state = get_runtime_mode()
        resolved_session_id, _, cookie_token = _resolve_request_session_id(
            request=request,
            mode_key=state.mode_key,
            server_url=state.active_server_url,
            explicit_session_id=payload.session_id,
        )
        auth_ctx = _AuthSessionContext(
            request=request, response=response, cookie_token=cookie_token
        )

        def _build_save_response(server_api_url: str) -> PolicySaveResponse:
            # Runtime config resolution happens per request so a stale/missing
            # session cannot be reused across save calls after mode/session
            # changes in the UI.
            runtime_config = resolve_runtime_config(
                session_id_override=resolved_session_id,
                base_url_override=server_api_url,
            )
            result = save_policy_variant_from_raw_content(
                selector=selector,
                raw_content=payload.raw_content,
                schema_version=payload.schema_version,
                status=payload.status,
                activate=payload.activate,
                world_id=payload.world_id,
                client_profile=payload.client_profile,
                actor=payload.actor,
                runtime_config=runtime_config,
            )
            return PolicySaveResponse(
                policy_id=result.policy_id,
                variant=result.variant,
                policy_version=result.policy_version,
                content_hash=result.content_hash,
                validation_run_id=result.validation_run_id,
                activated=payload.activate,
                activation_audit_event_id=result.activation_audit_event_id,
            )

        return _run_server_api_route(_build_save_response, auth_ctx=auth_ctx)

    return app
