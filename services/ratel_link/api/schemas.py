"""HTTP request and response bodies for RatelLink's endpoints (Contract 1)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, SecretStr

from ratel_link.domain.identifiers import IMSI_PATTERN
from ratel_link.domain.sim_keys import check_key_hex

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
