from __future__ import annotations

from fastapi import FastAPI

from app.bss_lines.api.lines import router as bss_lines_router
from app.config import Settings
from app.db import make_engine, session_factory
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
    app.state.session_factory = session_factory(
        make_engine(settings.database_url.get_secret_value())
    )

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        # Liveness only. TODO: readiness check (PostgreSQL, Redis) once models exist.
        return {"status": "ok"}

    # TODO: mount bss_money and meter_api routers as they are built.
    # Network access rules (RatelDesk and API only over the WireGuard VPN; RatelPay and the
    # payment webhook are the only public paths) are enforced at the reverse proxy and
    # documented in deploy/bss-app/README.md.
    app.include_router(bss_lines_router)
    return app
