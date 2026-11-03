"""Pydantic schemas matching contracts/openapi.yaml for RatelMeter."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _validate_non_negative_int(v: Any) -> int:
    if isinstance(v, bool):
        raise ValueError("Must be integer, not boolean")
    if isinstance(v, float):
        if not v.is_integer():
            raise ValueError("Must be integer, not fractional float")
        return int(v)
    if isinstance(v, int):
        return v
    raise ValueError("Must be integer")


NonNegativeInt = Annotated[int, BeforeValidator(_validate_non_negative_int), Field(ge=0)]


class UsageRecordSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    imsi: str = Field(..., pattern=r"^[0-9]{15}$", examples=["621000000000001"])
    period_start: NonNegativeInt = Field(..., description="Unix epoch seconds, UTC.")
    period_end: NonNegativeInt = Field(..., description="Unix epoch seconds, UTC.")
    bytes_up: NonNegativeInt = Field(...)
    bytes_down: NonNegativeInt = Field(...)


class UsageBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[UsageRecordSchema] = Field(..., min_length=1, max_length=5000)


class UsageListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[UsageRecordSchema] = Field(..., max_length=5000)
    next_cursor: str | None = None


EndReason = Literal["completed", "cancelled", "declined", "not_answered", "unavailable", "failed"]


class CallRecordSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str = Field(
        ..., pattern=r"^[!-~]{1,128}$", description="The SIP Call-ID. A replay overwrites."
    )
    from_msisdn: str = Field(..., pattern=r"^[!-~]{1,32}$")
    to_msisdn: str = Field(..., pattern=r"^[!-~]{1,32}$")
    started_at: NonNegativeInt = Field(..., description="Unix epoch seconds, UTC.")
    answered_at: NonNegativeInt | None = Field(
        ..., description="Null when the call was never answered."
    )
    ended_at: NonNegativeInt = Field(..., description="Unix epoch seconds, UTC.")
    end_reason: EndReason = Field(...)


class CallBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[CallRecordSchema] = Field(..., min_length=1, max_length=5000)


class CallListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[CallRecordSchema] = Field(..., max_length=5000)
    next_cursor: str | None = None
