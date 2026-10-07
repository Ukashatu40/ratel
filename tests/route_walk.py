"""List a FastAPI app's routes the way requests will see them, including included routers.

Recent FastAPI versions keep `include_router()` as a lazy wrapper instead of copying its routes
into `app.routes`, so a plain `for route in app.routes` silently misses every included route.
Tests that must see all routes (contract drift, route protection) use this instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

try:
    from fastapi.routing import iter_route_contexts
except ImportError:  # older FastAPI flattens included routers into app.routes itself
    iter_route_contexts = None  # type: ignore[assignment]


@dataclass(frozen=True)
class EffectiveRoute:
    path: str
    methods: frozenset[str]
    is_api_route: bool
    # The merged dependency tree: router-level and route-level dependencies together.
    dependant: Dependant | None


def effective_routes(app: FastAPI) -> list[EffectiveRoute]:
    if iter_route_contexts is None:
        return [
            EffectiveRoute(
                getattr(r, "path", repr(r)),
                frozenset(getattr(r, "methods", None) or ()),
                isinstance(r, APIRoute),
                getattr(r, "dependant", None),
            )
            for r in app.routes
        ]
    return [
        EffectiveRoute(
            ctx.path or repr(ctx.original_route),
            frozenset(ctx.methods or ()),
            isinstance(ctx.original_route, APIRoute),
            ctx.dependant if isinstance(ctx.original_route, APIRoute) else None,
        )
        for ctx in iter_route_contexts(app.routes)
    ]
