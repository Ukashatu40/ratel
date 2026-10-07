"""Contract drift detection between contracts/openapi.yaml and the FastAPI services.

1. No service may expose a route the contract does not describe (except operational endpoints).
2. Every contract operation is either implemented in the right service, or listed in
   contracts/not_implemented.txt. A listed operation that IS implemented fails too, so the list
   cannot go stale. Schemathesis (scripts/ci/run_schemathesis.sh) then fuzzes the implemented ones.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from app.config import Settings as AppSettings
from app.main import create_app as create_bss_app
from ratel_link.config import Settings as LinkSettings
from ratel_link.main import create_app as create_link_app
from tests.contract.helpers import not_implemented, operations
from tests.route_walk import effective_routes

OPERATIONAL = {("GET", "/healthz")}
TAG_FOR_SERVICE = {"ratel_link": "RatelLink", "app": "RatelMeter"}


def _services() -> dict[str, FastAPI]:
    return {"ratel_link": create_link_app(LinkSettings()), "app": create_bss_app(AppSettings())}


def _routes(app: FastAPI) -> set[tuple[str, str]]:
    # Includes routes added with include_router(), which `app.routes` alone does not list.
    return {(m, r.path) for r in effective_routes(app) if r.is_api_route for m in r.methods}


@pytest.mark.parametrize("service", sorted(TAG_FOR_SERVICE))
def test_service_exposes_no_undocumented_routes(service: str) -> None:
    tag = TAG_FOR_SERVICE[service]
    documented = {(o.method, o.path) for o in operations() if o.tag == tag}
    extra = _routes(_services()[service]) - OPERATIONAL - documented
    assert not extra, f"{service} has routes missing from contracts/openapi.yaml: {sorted(extra)}"


def test_not_implemented_list_has_no_unknown_ids() -> None:
    unknown = not_implemented() - {o.op_id for o in operations()}
    assert not unknown, (
        f"contracts/not_implemented.txt lists unknown operationIds: {sorted(unknown)}"
    )


def test_implemented_matches_not_implemented_list() -> None:
    services = _services()
    routes = {name: _routes(app) for name, app in services.items()}
    owner = {tag: svc for svc, tag in TAG_FOR_SERVICE.items()}
    skip = not_implemented()
    problems = []
    for o in operations():
        implemented = (o.method, o.path) in routes[owner[o.tag]]
        if o.op_id in skip and implemented:
            problems.append(f"{o.op_id} is implemented: remove it from not_implemented.txt")
        if o.op_id not in skip and not implemented:
            problems.append(
                f"{o.op_id} is not implemented: add it to not_implemented.txt or build it"
            )
    assert not problems, "\n".join(problems)


def test_drift_check_sees_routes_from_included_routers() -> None:
    # Without this, implementing an operation through an APIRouter would not be noticed.
    from fastapi import APIRouter

    app = create_link_app(LinkSettings())
    router = APIRouter(prefix="/v1")

    @router.post("/sims")
    def create_sim() -> dict[str, str]:
        return {}

    app.include_router(router)
    assert ("POST", "/v1/sims") in _routes(app)
