"""The /v1 router. Every Contract 1 route is added here and requires an API key by default."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ratel_link.api import assignments, lines, sims
from ratel_link.api.dependencies import AuthFirstRoute, require_api_key


def new_v1_router() -> APIRouter:
    """An empty /v1 router that already requires a valid API key. Routes added to it are
    protected by default (tests build their own routes on it)."""
    return APIRouter(
        prefix="/v1", dependencies=[Depends(require_api_key)], route_class=AuthFirstRoute
    )


def build_v1_router() -> APIRouter:
    """The /v1 router with every Contract 1 route that exists. Add new route modules here."""
    router = new_v1_router()
    sims.add_routes(router)
    lines.add_routes(router)
    assignments.add_routes(router)
    # TODO: deactivate (W2-02), after the barring spike (W2-05) decides bar or delete.
    return router
