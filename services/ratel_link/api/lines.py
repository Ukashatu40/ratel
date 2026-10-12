"""GET /v1/lines/{imsi}: a line's status (Contract 1, link_get_line). Never returns keys."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from common.errors import ApiError
from ratel_link.api.schemas import LineStatusResponse
from ratel_link.domain.identifiers import IMSI_PATTERN
from ratel_link.services.line_status import LineStatusService


def get_line_status_service(request: Request) -> LineStatusService:
    service: LineStatusService = request.app.state.line_status
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


def add_routes(router: APIRouter) -> None:
    router.add_api_route(
        "/lines/{imsi}",
        get_line,
        methods=["GET"],
        response_model=LineStatusResponse,
        operation_id="link_get_line",
    )
