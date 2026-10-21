"""HTTP routes for RatelMeter: data usage ingestion and query."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query

from common.errors import ApiError

from ..domain import UsageRecord
from ..repositories.ports import UsageRepository
from ..services.ingest import IngestService
from ..services.query import QueryService
from .dependencies import get_usage_repository, require_api_key
from .schemas import UsageBatchRequest, UsageListResponse, UsageRecordSchema

router = APIRouter(prefix="/v1", tags=["RatelMeter"])


@router.post(
    "/usage",
    operation_id="meter_ingest_usage",
    summary="Ingest a batch of data usage records.",
    dependencies=[Depends(require_api_key)],
    response_model=dict[str, Any],
)
def ingest_usage(
    body: UsageBatchRequest,
    repo: Annotated[UsageRepository, Depends(get_usage_repository)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    if idempotency_key is not None and not idempotency_key.strip():
        raise ApiError(422, "validation_error", "Idempotency-Key header must not be empty.")

    domain_records = [
        UsageRecord(
            imsi=r.imsi,
            period_start=r.period_start,
            period_end=r.period_end,
            bytes_up=r.bytes_up,
            bytes_down=r.bytes_down,
        )
        for r in body.records
    ]

    service = IngestService(repo)
    try:
        service.ingest_batch(domain_records)
    except ValueError as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc

    return {}


@router.get(
    "/usage",
    operation_id="meter_get_usage",
    summary="Data usage records (one per line per 300-second interval).",
    dependencies=[Depends(require_api_key)],
    response_model=UsageListResponse,
)
def get_usage(
    from_time: Annotated[int, Query(alias="from", ge=0, description="Unix epoch seconds, UTC.")],
    to_time: Annotated[int, Query(alias="to", ge=0, description="Unix epoch seconds, UTC.")],
    repo: Annotated[UsageRepository, Depends(get_usage_repository)],
    imsi: Annotated[str | None, Query(pattern=r"^[0-9]{15}$")] = None,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
) -> UsageListResponse:
    service = QueryService(repo)
    try:
        records, next_cursor = service.get_usage(
            from_epoch_sec=from_time,
            to_epoch_sec=to_time,
            imsi=imsi,
            limit=5000,
            cursor=cursor,
        )
    except ValueError as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc

    schemas = [
        UsageRecordSchema(
            imsi=r.imsi,
            period_start=r.period_start,
            period_end=r.period_end,
            bytes_up=r.bytes_up,
            bytes_down=r.bytes_down,
        )
        for r in records
    ]
    return UsageListResponse(records=schemas, next_cursor=next_cursor)
