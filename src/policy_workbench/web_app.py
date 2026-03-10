"""FastAPI application factory for the Phase 3 policy workbench UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __version__
from .sync_apply import apply_sync_plan
from .web_models import (
    PolicyFileResponse,
    PolicyFileUpdateRequest,
    PolicyFileUpdateResponse,
    PolicyTreeResponse,
    SyncApplyRequest,
    SyncApplyResponse,
    SyncCompareResponse,
    SyncPlanResponse,
    ValidationResponse,
)
from .web_services import (
    build_sync_compare_payload,
    build_sync_payload,
    build_sync_plan_for_apply,
    build_tree_payload,
    build_validation_payload,
    read_policy_file,
    resolve_source_root_for_web,
    write_policy_file,
)

_HERE = Path(__file__).resolve().parent
_TEMPLATES_DIR = _HERE / "templates"
_STATIC_DIR = _HERE / "static"


def create_web_app(
    *,
    source_root_override: str | None = None,
    map_path_override: str | None = None,
) -> FastAPI:
    """Create configured FastAPI app instance for UI and API routes."""

    app = FastAPI(title="Pipeworks Policy Workbench", version=__version__)

    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

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

    @app.get("/api/tree", response_model=PolicyTreeResponse)
    async def api_tree(
        root: str | None = Query(default=None),
        map_path: str | None = Query(default=None),
    ) -> PolicyTreeResponse:
        """Return canonical policy tree entries for the browser panel."""

        try:
            source_root = resolve_source_root_for_web(
                root_override=root or source_root_override,
                map_path_override=map_path or map_path_override,
            )
            return build_tree_payload(source_root)
        except (FileNotFoundError, NotADirectoryError, ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/file", response_model=PolicyFileResponse)
    async def api_file_read(
        relative_path: str = Query(min_length=1),
        root: str | None = Query(default=None),
        map_path: str | None = Query(default=None),
    ) -> PolicyFileResponse:
        """Read one source policy file by relative path."""

        try:
            source_root = resolve_source_root_for_web(
                root_override=root or source_root_override,
                map_path_override=map_path or map_path_override,
            )
            content = read_policy_file(source_root, relative_path)
            return PolicyFileResponse(
                source_root=str(source_root),
                relative_path=relative_path,
                content=content,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (IsADirectoryError, NotADirectoryError, ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.put("/api/file", response_model=PolicyFileUpdateResponse)
    async def api_file_write(
        payload: PolicyFileUpdateRequest,
        root: str | None = Query(default=None),
        map_path: str | None = Query(default=None),
    ) -> PolicyFileUpdateResponse:
        """Save one source policy file by relative path."""

        try:
            source_root = resolve_source_root_for_web(
                root_override=root or source_root_override,
                map_path_override=map_path or map_path_override,
            )
            bytes_written = write_policy_file(source_root, payload.relative_path, payload.content)
            return PolicyFileUpdateResponse(
                source_root=str(source_root),
                relative_path=payload.relative_path,
                bytes_written=bytes_written,
            )
        except (IsADirectoryError, NotADirectoryError, ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/validate", response_model=ValidationResponse)
    async def api_validate(
        root: str | None = Query(default=None),
        map_path: str | None = Query(default=None),
    ) -> ValidationResponse:
        """Return validation counts and issue rows for current source tree."""

        try:
            source_root = resolve_source_root_for_web(
                root_override=root or source_root_override,
                map_path_override=map_path or map_path_override,
            )
            return build_validation_payload(source_root)
        except (FileNotFoundError, NotADirectoryError, ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/sync-plan", response_model=SyncPlanResponse)
    async def api_sync_plan(
        include_unchanged: bool = Query(default=False),
        root: str | None = Query(default=None),
        map_path: str | None = Query(default=None),
    ) -> SyncPlanResponse:
        """Return dry-run sync plan for impact review panel."""

        try:
            source_root = resolve_source_root_for_web(
                root_override=root or source_root_override,
                map_path_override=map_path or map_path_override,
            )
            return build_sync_payload(
                source_root=source_root,
                map_path_override=map_path or map_path_override,
                include_unchanged=include_unchanged,
            )
        except (
            FileNotFoundError,
            IsADirectoryError,
            NotADirectoryError,
            ValueError,
            OSError,
        ) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/sync-compare", response_model=SyncCompareResponse)
    async def api_sync_compare(
        relative_path: str = Query(min_length=1),
        focus_target: str | None = Query(default=None),
        root: str | None = Query(default=None),
        map_path: str | None = Query(default=None),
    ) -> SyncCompareResponse:
        """Return side-by-side source/target comparison for one sync path."""

        try:
            source_root = resolve_source_root_for_web(
                root_override=root or source_root_override,
                map_path_override=map_path or map_path_override,
            )
            return build_sync_compare_payload(
                source_root=source_root,
                map_path_override=map_path or map_path_override,
                relative_path=relative_path,
                focus_target=focus_target,
            )
        except (IsADirectoryError, NotADirectoryError, ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/sync-apply", response_model=SyncApplyResponse)
    async def api_sync_apply(
        payload: SyncApplyRequest,
        root: str | None = Query(default=None),
        map_path: str | None = Query(default=None),
    ) -> SyncApplyResponse:
        """Apply non-destructive create/update actions from current sync plan."""

        if not payload.confirm:
            raise HTTPException(status_code=400, detail="Sync apply requires confirm=true")

        try:
            source_root = resolve_source_root_for_web(
                root_override=root or source_root_override,
                map_path_override=map_path or map_path_override,
            )
            plan = build_sync_plan_for_apply(
                source_root=source_root,
                map_path_override=map_path or map_path_override,
            )
            report = apply_sync_plan(plan)
            return SyncApplyResponse(
                created=report.created,
                updated=report.updated,
                skipped=report.skipped,
            )
        except (
            FileNotFoundError,
            IsADirectoryError,
            NotADirectoryError,
            ValueError,
            OSError,
        ) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app
