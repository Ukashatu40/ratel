"""Operations on one line (Contract 1): status, activate and data. Never returns keys.

`GET /v1/lines/{imsi}` (link_get_line), `POST /v1/lines/{imsi}/activate` (link_activate_line) and
`POST /v1/lines/{imsi}/data` (link_set_data_mode). The routes validate the request, call a service
and turn its errors into the standard error shape. The rules live in the services.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Path, Request

from common.errors import ApiError
from ratel_link.api.dependencies import require_api_key
from ratel_link.api.schemas import ActivateBody, DataBody, LineStatusResponse
from ratel_link.domain.identifiers import IMSI_PATTERN
from ratel_link.domain.ip_pool import PoolExhaustedError
from ratel_link.domain.subscriber import SpeedError
from ratel_link.services.authentication import ApiPrincipal
from ratel_link.services.data_mode import DataModeService, NoActiveLineError, SubscriberMissingError
from ratel_link.services.ip_allocation import AllocationContentionError
from ratel_link.services.line_activation import (
    LineActivationService,
    UnknownSimError,
    VoiceUnavailableError,
)
from ratel_link.services.line_status import LineStatusService

SPEED_MESSAGE = "Speeds must be greater than 0 and a whole number of bits per second."


def get_line_status_service(request: Request) -> LineStatusService:
    service: LineStatusService = request.app.state.line_status
    return service


def get_line_activation_service(request: Request) -> LineActivationService:
    service: LineActivationService = request.app.state.line_activation
    return service


def get_data_mode_service(request: Request) -> DataModeService:
    service: DataModeService = request.app.state.data_mode
    return service


def get_line(
    imsi: Annotated[str, Path(pattern=IMSI_PATTERN)],
    service: Annotated[LineStatusService, Depends(get_line_status_service)],
) -> LineStatusResponse:
    view = service.get(imsi)
    if view is None:
        raise ApiError(404, "not_found", "Unknown line.")
    return LineStatusResponse(
        status=view.status,
        msisdn=view.msisdn,
        apns=list(view.apns),
        ue_ip=view.ue_ip,
        speed_ul_mbps=view.speed_ul_mbps,
        speed_dl_mbps=view.speed_dl_mbps,
    )


def activate_line(
    imsi: Annotated[str, Path(pattern=IMSI_PATTERN)],
    body: ActivateBody,
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    service: Annotated[LineActivationService, Depends(get_line_activation_service)],
    idempotency_key: Annotated[str | None, Header(min_length=1)] = None,
) -> dict[str, Any]:
    """Write the line's subscriber document. Repeating it with the same settings changes nothing.

    A plain `def` on purpose: the storage calls block, so FastAPI runs this in a worker thread.
    The Idempotency-Key header is validated as the contract says and is not otherwise needed: the
    operation is idempotent by construction.
    """
    try:
        service.activate(
            imsi,
            body.msisdn,
            body.speed_ul_mbps,
            body.speed_dl_mbps,
            body.voice,
            principal.api_key_id,
        )
    except SpeedError:
        raise ApiError(422, "validation_error", SPEED_MESSAGE) from None
    except UnknownSimError:
        raise ApiError(404, "not_found", "Unknown line.") from None
    except VoiceUnavailableError:
        raise ApiError(503, "unavailable", "Voice cannot be switched on right now.") from None
    except (PoolExhaustedError, AllocationContentionError):
        raise ApiError(
            503, "unavailable", "No address can be given to the line right now."
        ) from None
    return {}


def set_data_mode(
    imsi: Annotated[str, Path(pattern=IMSI_PATTERN)],
    body: DataBody,
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    service: Annotated[DataModeService, Depends(get_data_mode_service)],
    idempotency_key: Annotated[str | None, Header(min_length=1)] = None,
) -> dict[str, Any]:
    """Change the internet APN only. Calling is untouched. Repeating it changes nothing."""
    try:
        service.set_mode(
            imsi, body.mode, body.speed_ul_mbps, body.speed_dl_mbps, principal.api_key_id
        )
    except SpeedError:
        raise ApiError(422, "validation_error", SPEED_MESSAGE) from None
    except NoActiveLineError:
        raise ApiError(404, "not_found", "No active line for this IMSI.") from None
    except SubscriberMissingError:
        raise ApiError(
            409, "conflict", "The network has no record for this line. Activate it again."
        ) from None
    return {}


def add_routes(router: APIRouter) -> None:
    router.add_api_route(
        "/lines/{imsi}",
        get_line,
        methods=["GET"],
        response_model=LineStatusResponse,
        operation_id="link_get_line",
    )
    router.add_api_route(
        "/lines/{imsi}/activate",
        activate_line,
        methods=["POST"],
        operation_id="link_activate_line",
        status_code=200,
    )
    router.add_api_route(
        "/lines/{imsi}/data",
        set_data_mode,
        methods=["POST"],
        operation_id="link_set_data_mode",
        status_code=200,
    )
