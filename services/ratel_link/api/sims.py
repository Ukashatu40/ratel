"""POST /v1/sims: store a SIM's keys (Contract 1, operation link_create_sim).

Keys are write-only: nothing here returns them, logs them or puts them in an error. The route
validates the body, calls the import service and shapes the answer. Rules live in the service.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request

from common.errors import ApiError
from ratel_link.api.dependencies import require_api_key
from ratel_link.api.schemas import SimImport
from ratel_link.services.authentication import ApiPrincipal
from ratel_link.services.sim_import import SimImportService, SimKeysConflictError


def get_sim_import_service(request: Request) -> SimImportService:
    service: SimImportService = request.app.state.sim_import
    return service


def create_sim(
    body: SimImport,
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    service: Annotated[SimImportService, Depends(get_sim_import_service)],
    idempotency_key: Annotated[str | None, Header(min_length=1)] = None,
) -> dict[str, Any]:
    """Store the keys. The same keys again succeed and change nothing; different keys are refused.

    A plain `def` on purpose: the storage calls block, so FastAPI runs this in a worker thread.
    The Idempotency-Key header is validated as the contract says (not empty when present) and is
    not otherwise needed here: this operation is idempotent by design (the same IMSI with the same
    keys is a no-op).
    """
    try:
        service.import_sim(body.imsi, body.ki, body.opc, principal.api_key_id)
    except SimKeysConflictError:
        raise ApiError(
            409, "conflict", "SIM keys are already stored for this IMSI with different values."
        ) from None
    return {}


def add_routes(router: APIRouter) -> None:
    router.add_api_route(
        "/sims", create_sim, methods=["POST"], operation_id="link_create_sim", status_code=200
    )
