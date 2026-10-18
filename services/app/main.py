from __future__ import annotations

from fastapi import FastAPI

from app.bss_lines.api import router as bss_lines_router
from app.config import Settings
from app.db import make_engine, session_factory
from common.errors import install_error_handlers
from common.http import install_request_context
from common.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="Ratel app",
        version="0.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    install_error_handlers(app)
    install_request_context(app)

    # One session factory for the whole app. The API layer reads it from app.state.
    app.state.session_factory = session_factory(
        make_engine(settings.database_url.get_secret_value())
    )

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(bss_lines_router)
    return app
