"""HTTP routes for RatelMeter: data usage ingestion and query."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query

from common.errors import ApiError

from ..domain import CallRecord, UsageRecord
from ..repositories.ports import CallRepository, UsageRepository
from ..services.calls import CallIngestService, CallQueryService
from ..services.ingest import IngestService
from ..services.query import QueryService
from .dependencies import get_call_repository, get_usage_repository, require_api_key
from .schemas import (
    CallBatchRequest,
    CallListResponse,
    CallRecordSchema,
    UsageBatchRequest,
    UsageListResponse,
    UsageRecordSchema,
)

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


@router.post(
    "/calls",
    operation_id="meter_ingest_calls",
    summary="Ingest a batch of call records.",
    dependencies=[Depends(require_api_key)],
    response_model=dict[str, Any],
)
def ingest_calls(
    body: CallBatchRequest,
    repo: Annotated[CallRepository, Depends(get_call_repository)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    if idempotency_key is not None and not idempotency_key.strip():
        raise ApiError(422, "validation_error", "Idempotency-Key header must not be empty.")
    records = [
        CallRecord(
            call_id=r.call_id,
            from_msisdn=r.from_msisdn,
            to_msisdn=r.to_msisdn,
            started_at=r.started_at,
            answered_at=r.answered_at,
            ended_at=r.ended_at,
            end_reason=r.end_reason,
        )
        for r in body.records
    ]
    try:
        CallIngestService(repo).ingest_batch(records)
    except ValueError as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc
    return {}


@router.get(
    "/calls",
    operation_id="meter_get_calls",
    summary="Call records (one per call).",
    dependencies=[Depends(require_api_key)],
    response_model=CallListResponse,
)
def get_calls(
    from_time: Annotated[int, Query(alias="from", ge=0, description="Unix epoch seconds, UTC.")],
    to_time: Annotated[int, Query(alias="to", ge=0, description="Unix epoch seconds, UTC.")],
    repo: Annotated[CallRepository, Depends(get_call_repository)],
    msisdn: Annotated[str | None, Query(pattern=r"^[!-~]{1,32}$")] = None,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
) -> CallListResponse:
    try:
        records, next_cursor = CallQueryService(repo).get_calls(
            from_epoch_sec=from_time, to_epoch_sec=to_time, msisdn=msisdn, cursor=cursor
        )
    except ValueError as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc
    return CallListResponse(
        records=[
            CallRecordSchema(
                call_id=r.call_id,
                from_msisdn=r.from_msisdn,
                to_msisdn=r.to_msisdn,
                started_at=r.started_at,
                answered_at=r.answered_at,
                ended_at=r.ended_at,
                end_reason=r.end_reason,  # type: ignore[arg-type]
            )
            for r in records
        ],
        next_cursor=next_cursor,
    )
