"""A line's state as RatelLink last wrote it to RatelCore (Build Plan: the `line_state` collection).

`status` is `provisioned` (keys stored, no service), `active` (subscriber document written) or
`barred`. Pure: no I/O, and no key material of any kind.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

LineStatusName = Literal["provisioned", "active", "barred"]
DataMode = Literal["full", "slow", "off"]


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class LineState:
    imsi: str
    status: LineStatusName
    updated_at: datetime
    msisdn: str | None = None
    apns: tuple[str, ...] = ()
    ue_ip: str | None = None
    speed_ul_mbps: float | None = None
    speed_dl_mbps: float | None = None
    data_mode: DataMode | None = None

    def to_document(self) -> dict[str, Any]:
        return {
            "imsi": self.imsi,
            "status": self.status,
            "msisdn": self.msisdn,
            "apns": list(self.apns),
            "ue_ip": self.ue_ip,
            "speed_ul_mbps": self.speed_ul_mbps,
            "speed_dl_mbps": self.speed_dl_mbps,
            "data_mode": self.data_mode,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> LineState:
        return cls(
            imsi=doc["imsi"],
            status=doc["status"],
            updated_at=_utc(doc["updated_at"]),
            msisdn=doc.get("msisdn"),
            apns=tuple(doc.get("apns") or ()),
            ue_ip=doc.get("ue_ip"),
            speed_ul_mbps=doc.get("speed_ul_mbps"),
            speed_dl_mbps=doc.get("speed_dl_mbps"),
            data_mode=doc.get("data_mode"),
        )


@dataclass(frozen=True, slots=True)
class LineView:
    """What `GET /v1/lines/{imsi}` reports: status, APNs, address, speeds and MSISDN. Never keys."""

    status: LineStatusName
    msisdn: str | None = None
    apns: tuple[str, ...] = ()
    ue_ip: str | None = None
    speed_ul_mbps: float | None = None
    speed_dl_mbps: float | None = None

    @classmethod
    def provisioned(cls) -> LineView:
        """A SIM whose keys are stored but which has no service yet."""
        return cls(status="provisioned")

    @classmethod
    def from_state(cls, state: LineState) -> LineView:
        return cls(
            status=state.status,
            msisdn=state.msisdn,
            apns=state.apns,
            ue_ip=state.ue_ip,
            speed_ul_mbps=state.speed_ul_mbps,
            speed_dl_mbps=state.speed_dl_mbps,
        )
