"""FastAPI application factory for the Phase 3 policy workbench UI."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import NoReturn, TypeVar

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __version__
from .policy_authoring import (
    PolicySelector,
    resolve_runtime_config,
    save_policy_variant_from_raw_content,
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
    RuntimeAuthResponse,
    RuntimeLoginRequest,
    RuntimeLoginResponse,
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


def create_web_app(
    *,
    source_root_override: str | None = None,
    map_path_override: str | None = None,
) -> FastAPI:
    """Create configured FastAPI app instance for UI and API routes."""

    app = FastAPI(title="Pipeworks Policy Workbench", version=__version__)

    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

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

    def _raise_mud_service_http_error(exc: ValueError | OSError) -> NoReturn:
        """Raise one normalized HTTPException for mud-service failures."""

        detail = str(exc)
        raise HTTPException(
            status_code=_status_code_for_mud_api_error(detail),
            detail=detail,
        ) from exc

    def _run_mud_service(call: Callable[[], _ResponseT]) -> _ResponseT:
        """Execute one mud-service call and normalize ValueError/OSError mapping."""

        try:
            return call()
        except (ValueError, OSError) as exc:
            _raise_mud_service_http_error(exc)

    def _run_server_api_route(call: Callable[[str], _ResponseT]) -> _ResponseT:
        """Resolve active server URL and execute one mud-server-backed route action."""

        try:
            server_api_url = require_server_api_url()
            return _run_mud_service(lambda: call(server_api_url))
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
        session_id: str | None = Query(default=None),
    ) -> RuntimeAuthResponse:
        """Return explicit runtime auth/access status for server-backed operations."""
        state = get_runtime_mode()
        return build_runtime_auth_payload(
            mode_key=state.mode_key,
            source_kind=state.source_kind,
            active_server_url=state.active_server_url,
            session_id_override=session_id,
            base_url_override=state.active_server_url,
        )

    @app.post("/api/runtime-login", response_model=RuntimeLoginResponse)
    async def api_runtime_login(payload: RuntimeLoginRequest) -> RuntimeLoginResponse:
        """Authenticate to active mud-server profile and return session bootstrap data."""
        state = get_runtime_mode()
        return _run_mud_service(
            lambda: build_runtime_login_payload(
                mode_key=state.mode_key,
                source_kind=state.source_kind,
                active_server_url=state.active_server_url,
                username=payload.username,
                password=payload.password,
                base_url_override=state.active_server_url,
            )
        )

    @app.get("/api/policy-types", response_model=PolicyTypeOptionsResponse)
    async def api_policy_types(
        session_id: str | None = Query(default=None),
    ) -> PolicyTypeOptionsResponse:
        """Return canonical policy-type options for inventory filtering."""
        state = get_runtime_mode()
        return _run_mud_service(
            lambda: build_policy_type_options_payload(
                source_kind=state.source_kind,
                active_server_url=state.active_server_url,
                session_id_override=session_id,
                base_url_override=state.active_server_url,
            )
        )

    @app.get("/api/policy-namespaces", response_model=PolicyTypeOptionsResponse)
    async def api_policy_namespaces(
        policy_type: str | None = Query(default=None),
        session_id: str | None = Query(default=None),
    ) -> PolicyTypeOptionsResponse:
        """Return canonical policy namespace options for inventory filtering."""
        state = get_runtime_mode()
        return _run_mud_service(
            lambda: build_policy_namespace_options_payload(
                source_kind=state.source_kind,
                active_server_url=state.active_server_url,
                session_id_override=session_id,
                policy_type=policy_type,
                base_url_override=state.active_server_url,
            )
        )

    @app.get("/api/policy-statuses", response_model=PolicyTypeOptionsResponse)
    async def api_policy_statuses(
        session_id: str | None = Query(default=None),
    ) -> PolicyTypeOptionsResponse:
        """Return canonical policy status options for inventory filtering."""
        state = get_runtime_mode()
        return _run_mud_service(
            lambda: build_policy_status_options_payload(
                source_kind=state.source_kind,
                active_server_url=state.active_server_url,
                session_id_override=session_id,
                base_url_override=state.active_server_url,
            )
        )

    @app.get("/api/policies", response_model=PolicyInventoryResponse)
    async def api_policies(
        policy_type: str | None = Query(default=None),
        namespace: str | None = Query(default=None),
        status: str | None = Query(default=None),
        session_id: str | None = Query(default=None),
    ) -> PolicyInventoryResponse:
        """Return API-first policy inventory list from mud-server canonical API."""

        return _run_server_api_route(
            lambda server_api_url: build_policy_inventory_payload(
                policy_type=policy_type,
                namespace=namespace,
                status=status,
                session_id_override=session_id,
                base_url_override=server_api_url,
            )
        )

    @app.get("/api/policies/{policy_id}", response_model=PolicyObjectDetailResponse)
    async def api_policy_detail(
        policy_id: str,
        variant: str | None = Query(default=None),
        session_id: str | None = Query(default=None),
    ) -> PolicyObjectDetailResponse:
        """Return one policy object detail payload from mud-server canonical API."""

        return _run_server_api_route(
            lambda server_api_url: build_policy_object_detail_payload(
                policy_id=policy_id,
                variant=variant,
                session_id_override=session_id,
                base_url_override=server_api_url,
            )
        )

    @app.get("/api/policy-activations-live", response_model=PolicyActivationScopeResponse)
    async def api_policy_activations_live(
        scope: str = Query(min_length=1),
        effective: bool = Query(default=True),
        session_id: str | None = Query(default=None),
    ) -> PolicyActivationScopeResponse:
        """Return scoped activation mappings from mud-server canonical API."""

        return _run_server_api_route(
            lambda server_api_url: build_policy_activation_scope_payload(
                scope=scope,
                effective=effective,
                session_id_override=session_id,
                base_url_override=server_api_url,
            )
        )

    @app.post("/api/policy-activation-set", response_model=PolicyActivationSetResponse)
    async def api_policy_activation_set(
        payload: PolicyActivationSetRequest,
    ) -> PolicyActivationSetResponse:
        """Set one activation pointer through mud-server canonical policy activation API."""

        return _run_server_api_route(
            lambda server_api_url: build_policy_activation_set_payload(
                world_id=payload.world_id,
                client_profile=payload.client_profile,
                policy_id=payload.policy_id,
                variant=payload.variant,
                activated_by=payload.activated_by,
                session_id_override=payload.session_id,
                base_url_override=server_api_url,
            )
        )

    @app.get(
        "/api/policy-publish-runs/{publish_run_id}",
        response_model=PolicyPublishRunProxyResponse,
    )
    async def api_policy_publish_run(
        publish_run_id: int,
        session_id: str | None = Query(default=None),
    ) -> PolicyPublishRunProxyResponse:
        """Return one publish run payload from mud-server canonical publish API."""

        return _run_server_api_route(
            lambda server_api_url: build_policy_publish_run_payload(
                publish_run_id=publish_run_id,
                session_id_override=session_id,
                base_url_override=server_api_url,
            )
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

    @app.post("/api/policy-save", response_model=PolicySaveResponse)
    async def api_policy_save(payload: PolicySaveRequest) -> PolicySaveResponse:
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

        def _build_save_response(server_api_url: str) -> PolicySaveResponse:
            # Runtime config resolution happens per request so a stale/missing
            # session cannot be reused across save calls after mode/session
            # changes in the UI.
            runtime_config = resolve_runtime_config(
                session_id_override=payload.session_id,
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

        return _run_server_api_route(_build_save_response)

    return app
