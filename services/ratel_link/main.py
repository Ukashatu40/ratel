from __future__ import annotations

from fastapi import FastAPI

from common.errors import install_error_handlers
from common.http import install_request_context
from common.logging import configure_logging
from ratel_link.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="RatelLink", version="0.0.0", docs_url=None, redoc_url=None, openapi_url=None
    )
    install_error_handlers(app)
    install_request_context(app)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        # Liveness only. TODO: readiness check (MongoDB ping) once RatelLink has a store.
        return {"status": "ok"}

    # TODO: Contract 1 routers (/v1/sims, /v1/lines/{imsi}/..., /v1/assignments).
    return app
