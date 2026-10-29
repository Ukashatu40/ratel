"""Every /v1 route of the app needs a credential: a staff session, or one of the two API keys.

This walks the real app's routes, so a route added later without protection fails the build,
whoever adds it and however. (RatelLink has the same test for its own app.)
"""

from __future__ import annotations

from fastapi.dependencies.models import Dependant

from app.bss_lines.api.deps import current_staff
from app.bss_money.api.dependencies import require_pay_key
from app.main import create_app
from app.meter_api.api.dependencies import require_api_key
from tests.route_walk import effective_routes

PROTECTION = {current_staff, require_pay_key, require_api_key}
# Public on purpose: liveness; readiness (a monitor has no key; it answers only ready or not, and
# the proxy does not forward it); sign-in (it is how a session starts); sign-out (ends one, and is
# harmless without one).
ALLOWLIST = {"/healthz", "/readyz", "/v1/auth/login", "/v1/auth/logout"}


def _protected(dependant: Dependant) -> bool:
    return any(d.call in PROTECTION or _protected(d) for d in dependant.dependencies)


def test_every_route_is_protected_or_allowlisted() -> None:
    problems = []
    for route in effective_routes(create_app()):
        where = f"{sorted(route.methods)} {route.path}"
        if route.path in ALLOWLIST:
            continue
        if not route.is_api_route or route.dependant is None or not _protected(route.dependant):
            problems.append(where)
    assert problems == []


def test_the_allowlist_names_only_routes_that_exist() -> None:
    assert ALLOWLIST <= {r.path for r in effective_routes(create_app())}
