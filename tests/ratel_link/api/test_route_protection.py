"""Every /v1 route must require an API key. This walks the real app's routes, so a route added
later without protection fails the build, whoever adds it and however."""

from __future__ import annotations

import ast
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.dependencies.models import Dependant

from ratel_link.api.dependencies import require_api_key
from ratel_link.api.router import new_v1_router
from ratel_link.config import Settings
from ratel_link.main import create_app
from tests.ratel_link.fakes import (
    FakeClock,
    InMemoryApiKeyRepository,
    InMemoryAuditLogRepository,
    InMemorySimKeyRepository,
)
from tests.route_walk import effective_routes

# Routes that are public on purpose. /healthz is liveness only and exposes nothing.
UNPROTECTED_ALLOWLIST = {"/healthz"}
PACKAGE = Path(__file__).resolve().parents[3] / "services" / "ratel_link"
MAIN = PACKAGE / "main.py"
ROUTER = PACKAGE / "api" / "router.py"


def _requires_key(dependant: Dependant) -> bool:
    return any(d.call is require_api_key or _requires_key(d) for d in dependant.dependencies)


def _is_v1(path: str) -> bool:
    return path == "/v1" or path.startswith("/v1/")


def unprotected_routes(app: FastAPI) -> list[str]:
    """Describe every route that is neither a key-protected /v1 route nor allowlisted."""
    problems = []
    for route in effective_routes(app):
        where = f"{sorted(route.methods)} {route.path}"
        if not route.is_api_route:
            problems.append(f"{where}: not an API route, so protection cannot be verified")
        elif _is_v1(route.path):
            if route.dependant is None or not _requires_key(route.dependant):
                problems.append(f"{where}: /v1 route without require_api_key")
        elif route.path not in UNPROTECTED_ALLOWLIST:
            problems.append(f"{where}: not under /v1 and not allowlisted")
    return problems


def _app() -> FastAPI:
    return create_app(
        Settings(),
        api_keys=InMemoryApiKeyRepository(),
        sim_keys=InMemorySimKeyRepository(),
        audit=InMemoryAuditLogRepository(),
        clock=FakeClock(),
    )


def test_every_route_of_the_real_app_is_protected_or_allowlisted() -> None:
    assert unprotected_routes(_app()) == []


def test_the_real_app_exposes_only_what_is_expected() -> None:
    paths = {r.path for r in effective_routes(_app())}
    assert UNPROTECTED_ALLOWLIST <= paths
    assert not any(p in paths for p in ("/docs", "/redoc", "/openapi.json"))


def test_a_route_added_to_the_v1_router_is_protected_by_default() -> None:
    router = new_v1_router()

    @router.get("/probe")
    def probe() -> dict[str, str]:  # declares no dependency of its own
        return {"ok": "yes"}

    app = _app()
    app.include_router(router)
    assert unprotected_routes(app) == []
    probe_route = next(r for r in effective_routes(app) if r.path == "/v1/probe")
    assert probe_route.dependant is not None and _requires_key(probe_route.dependant)


# --- the ratchet can fail ----------------------------------------------------------------------


def test_the_checker_flags_an_unprotected_v1_route() -> None:
    app = _app()
    rogue = APIRouter(prefix="/v1")  # someone forgets the dependency

    @rogue.get("/rogue")
    def rogue_route() -> dict[str, str]:
        return {"oops": "open"}

    app.include_router(rogue)
    problems = unprotected_routes(app)
    assert len(problems) == 1 and "/v1/rogue" in problems[0]


def test_the_checker_flags_a_route_added_straight_to_the_app() -> None:
    app = _app()

    @app.get("/v1/direct")
    def direct() -> dict[str, str]:
        return {"oops": "open"}

    assert any("/v1/direct" in p for p in unprotected_routes(app))


def test_the_checker_flags_an_extra_public_route_outside_v1() -> None:
    app = _app()

    @app.get("/admin")
    def admin() -> dict[str, str]:
        return {"oops": "open"}

    assert any("/admin" in p for p in unprotected_routes(app))


def test_the_checker_flags_a_mounted_app() -> None:
    app = _app()
    app.mount("/v1/static", FastAPI())
    assert any("/v1/static" in p for p in unprotected_routes(app))


# --- the wiring in api/router.py and main.py ---------------------------------------------------


def test_the_v1_router_has_the_key_dependency_and_main_includes_it() -> None:
    router_calls = [n for n in ast.walk(ast.parse(ROUTER.read_text())) if isinstance(n, ast.Call)]
    routers = [c for c in router_calls if getattr(c.func, "id", "") == "APIRouter"]
    assert len(routers) == 1, "api/router.py must create exactly one APIRouter"
    kwargs = {k.arg: ast.unparse(k.value) for k in routers[0].keywords}
    assert kwargs["prefix"] == "'/v1'"
    assert "Depends(require_api_key)" in kwargs["dependencies"]
    assert kwargs["route_class"] == "AuthFirstRoute"

    main_calls = [n for n in ast.walk(ast.parse(MAIN.read_text())) if isinstance(n, ast.Call)]
    assert not [c for c in main_calls if getattr(c.func, "id", "") == "APIRouter"], (
        "main.py must not build its own router: routes are added in api/router.py"
    )
    includes = [
        ast.unparse(c) for c in main_calls if getattr(c.func, "attr", "") == "include_router"
    ]
    assert includes == ["app.include_router(build_v1_router())"]


def test_the_walker_sees_routes_from_included_routers() -> None:
    # Guards the helper itself: if it ever stops looking inside included routers, the checks
    # above would pass vacuously.
    router = new_v1_router()

    @router.get("/seen")
    def seen() -> dict[str, str]:
        return {}

    app = _app()
    app.include_router(router)
    assert "/v1/seen" in {r.path for r in effective_routes(app)}
