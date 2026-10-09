"""The /v1 router. Every Contract 1 route is added here and requires an API key by default."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ratel_link.api.dependencies import AuthFirstRoute, require_api_key


def new_v1_router() -> APIRouter:
    """The router for every /v1 route. Add Contract 1 routes here (/v1/sims,
    /v1/lines/{imsi}/..., /v1/assignments) and they require a valid API key by default."""
    return APIRouter(
        prefix="/v1", dependencies=[Depends(require_api_key)], route_class=AuthFirstRoute
    )
