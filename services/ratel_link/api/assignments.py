"""GET /v1/assignments: every current IP address with its IMSI, for RatelMeter's agent."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from ratel_link.api.schemas import AssignmentItem, AssignmentListResponse
from ratel_link.services.assignments import AssignmentService


def get_assignment_service(request: Request) -> AssignmentService:
    service: AssignmentService = request.app.state.assignments
    return service


def list_assignments(
    service: Annotated[AssignmentService, Depends(get_assignment_service)],
) -> AssignmentListResponse:
    return AssignmentListResponse(
        assignments=[AssignmentItem(ue_ip=a.ue_ip, imsi=a.imsi) for a in service.list_current()]
    )


def add_routes(router: APIRouter) -> None:
    router.add_api_route(
        "/assignments",
        list_assignments,
        methods=["GET"],
        response_model=AssignmentListResponse,
        operation_id="link_list_assignments",
    )
