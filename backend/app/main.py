from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.ai.evaluation import EvaluationProvider
from app.ai.openai_compatible import build_roleplay_provider
from app.ai.openai_compatible_evaluation import build_evaluation_provider
from app.ai.roleplay import RoleplayProvider
from app.api.deps import PracticeAccessError, get_database_health
from app.api.errors import error_response
from app.api.practice import router as practice_router
from app.api.review import router as review_router
from app.api.scenarios import router as scenarios_router
from app.core.config import settings


def create_app(
    database_url: str | None = None,
    roleplay_provider: RoleplayProvider | None = None,
    evaluation_provider: EvaluationProvider | None = None,
) -> FastAPI:
    """Build the application.

    ``roleplay_provider`` and ``evaluation_provider`` are explicit seams for tests: when passed, the
    app
    uses them as-is and leaves their lifecycle to the caller. Otherwise each is built from settings
    at
    startup, so a misconfigured deployment fails to start instead of failing on the first user turn,
    and
    the HTTP clients they own are closed on shutdown.
    """
    if settings.app_env != "local":
        raise RuntimeError(
            "Voxora MVP requires local mode until full user authentication is implemented."
        )
    resolved_database_url = database_url or settings.database_url

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_async_engine(resolved_database_url, pool_pre_ping=True)
        app.state.database_engine = engine
        app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
        roleplay = roleplay_provider or build_roleplay_provider(settings)
        evaluation = evaluation_provider or build_evaluation_provider(settings)
        app.state.roleplay_provider = roleplay
        app.state.evaluation_provider = evaluation
        try:
            yield
        finally:
            if roleplay_provider is None:
                await roleplay.aclose()
            if evaluation_provider is None:
                await evaluation.aclose()
            await engine.dispose()

    app = FastAPI(title="Voxora API", version=settings.app_version, lifespan=lifespan)
    app.include_router(scenarios_router)
    app.include_router(practice_router)
    app.include_router(review_router)

    @app.exception_handler(PracticeAccessError)
    async def handle_practice_access_error(
        request: Request, exc: PracticeAccessError
    ) -> JSONResponse:
        return error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )

    @app.middleware("http")
    async def add_request_id(request: Request, call_next) -> Response:
        supplied_request_id = request.headers.get("X-Request-ID")
        try:
            request_id = str(UUID(supplied_request_id)) if supplied_request_id else str(uuid4())
        except ValueError:
            request_id = str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.get("/api/v1/health")
    async def health(request: Request, database: str = Depends(get_database_health)) -> Response:
        if database != "ok":
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "service_unavailable",
                        "message": "Database is unavailable.",
                        "request_id": request.state.request_id,
                        "details": {},
                    }
                },
            )
        return JSONResponse(
            content={"status": "ok", "database": "ok", "version": settings.app_version}
        )

    return app


app = create_app()
