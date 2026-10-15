"""HTTP request and response bodies for RatelLink's endpoints (Contract 1)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StrictBool,
    model_validator,
)

from ratel_link.domain.identifiers import IMSI_PATTERN, MSISDN_PATTERN
from ratel_link.domain.sim_keys import check_key_hex
from ratel_link.domain.subscriber import MAX_SPEED_MBPS, SpeedError, speed_from_mbps

KeyHex = Annotated[SecretStr, AfterValidator(check_key_hex)]


class SimImport(BaseModel):
    """Body of POST /v1/sims (contract: SimImport)."""

    # hide_input_in_errors: a validation error must never echo a rejected Ki or OPc.
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    imsi: str = Field(pattern=IMSI_PATTERN)
    ki: KeyHex
    opc: KeyHex


class LineStatusResponse(BaseModel):
    """Body of GET /v1/lines/{imsi} (contract: LineStatus). Exactly these fields, never keys."""

    status: Literal["provisioned", "active", "barred"]
    msisdn: str | None
    apns: list[str]
    ue_ip: str | None
    speed_ul_mbps: float | None
    speed_dl_mbps: float | None


class AssignmentItem(BaseModel):
    ue_ip: str
    imsi: str


class AssignmentListResponse(BaseModel):
    """Body of GET /v1/assignments (contract: AssignmentList)."""

    assignments: list[AssignmentItem]


# Strict: a JSON string such as "10" or a boolean is not a number, whatever lax parsing would do.
# A speed is greater than zero, at most MAX_SPEED_MBPS and a whole number of bits per second. It is
# checked here whenever it is present, even in a request that will not use it (data `off`).
def _whole_bits_per_second(value: float) -> float:
    try:
        speed_from_mbps(value)
    except SpeedError:
        raise ValueError("speed must be a whole number of bits per second") from None
    return value


Speed = Annotated[
    float,
    Field(strict=True, gt=0, le=MAX_SPEED_MBPS, allow_inf_nan=False),
    AfterValidator(_whole_bits_per_second),
]


class ActivateBody(BaseModel):
    """Body of POST /v1/lines/{imsi}/activate (contract: ActivateRequest)."""

    model_config = ConfigDict(extra="forbid")

    msisdn: str = Field(pattern=MSISDN_PATTERN)
    speed_ul_mbps: Speed
    speed_dl_mbps: Speed
    voice: StrictBool


class DataBody(BaseModel):
    """Body of POST /v1/lines/{imsi}/data (contract: DataRequest)."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["full", "slow", "off"]
    speed_ul_mbps: Speed | None = None
    speed_dl_mbps: Speed | None = None

    @model_validator(mode="before")
    @classmethod
    def _a_speed_is_left_out_or_a_number(cls, data: Any) -> Any:
        # The contract allows leaving a speed out, but not sending it as null.
        if isinstance(data, dict) and any(
            name in data and data[name] is None for name in ("speed_ul_mbps", "speed_dl_mbps")
        ):
            raise ValueError("a speed must be a number when it is present")
        return data
