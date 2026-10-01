from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_database_health
from app.api.scenarios import router as scenarios_router
from app.core.config import settings


def create_app(database_url: str | None = None) -> FastAPI:
    resolved_database_url = database_url or settings.database_url

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_async_engine(resolved_database_url, pool_pre_ping=True)
        app.state.database_engine = engine
        app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="Voxora API", version=settings.app_version, lifespan=lifespan)
    app.include_router(scenarios_router)

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
