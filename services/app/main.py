from typing import Any, cast

from fastapi import FastAPI, Request, Response

from app.config import Settings
from app.db import make_engine, session_factory
from app.meter_api.api import router as meter_router
from common.errors import install_error_handlers
from common.http import install_request_context
from common.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="Ratel app", version="0.0.0", docs_url=None, redoc_url=None, openapi_url=None
    )
    install_error_handlers(app)
    install_request_context(app)

    app.state.settings = settings
    db_url = settings.database_url.get_secret_value()
    if db_url.startswith("sqlite"):
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool

        engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = make_engine(db_url)
    app.state.engine = engine
    app.state.session_factory = session_factory(engine)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        # Liveness only. TODO: readiness check (PostgreSQL, Redis) once models exist.
        return {"status": "ok"}

    @app.middleware("http")
    async def _handle_options(request: Request, call_next: Any) -> Response:
        if request.method == "OPTIONS" and request.url.path == "/v1/usage":
            return Response(status_code=200, headers={"Allow": "GET, POST, OPTIONS"})
        return cast(Response, await call_next(request))

    app.include_router(meter_router)
    return app
