"""In-memory RatelLinkClient for tests.

Records every call so we can assert "exactly one /activate".
A repeat with the same key AND endpoint does not record a second call (mirrors what
RatelLink promises by body, in the contract).
Can be told to fail, for error-path tests.

TODO(idempotency, M-26): the real HTTP API currently returns 400 on a
repeat with the same key (the state machine refuses active -> active).
Returning the *original response* for a repeat needs a key store,
planned for M-26. This fake does not simulate that yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RecordedActivate:
    endpoint: str
    imsi: str
    msisdn: str
    speed_ul_mbps: float
    speed_dl_mbps: float
    voice: bool
    idempotency_key: str


@dataclass
class RecordedDeactivate:
    endpoint: str
    imsi: str
    reason: str
    idempotency_key: str


@dataclass
class RecordedData:
    endpoint: str
    imsi: str
    mode: str
    speed_ul_mbps: float | None
    speed_dl_mbps: float | None
    idempotency_key: str


Recorded = RecordedActivate | RecordedDeactivate | RecordedData


@dataclass
class FakeRatelLinkClient:
    calls: list[Recorded] = field(default_factory=list)
    _by_key: dict[tuple[str, str], Recorded] = field(default_factory=dict)
    fail_on_activate: Exception | None = None
    fail_on_deactivate: Exception | None = None
    fail_on_data: Exception | None = None

    def activate(
        self,
        imsi: str,
        *,
        msisdn: str,
        speed_ul_mbps: float,
        speed_dl_mbps: float,
        voice: bool,
        idempotency_key: str,
    ) -> None:
        if self.fail_on_activate is not None:
            raise self.fail_on_activate
        key = ("/activate", idempotency_key)
        if key in self._by_key:
            return
        call = RecordedActivate(
            endpoint="/activate",
            imsi=imsi,
            msisdn=msisdn,
            speed_ul_mbps=speed_ul_mbps,
            speed_dl_mbps=speed_dl_mbps,
            voice=voice,
            idempotency_key=idempotency_key,
        )
        self.calls.append(call)
        self._by_key[key] = call

    def deactivate(
        self,
        imsi: str,
        *,
        reason: str,
        idempotency_key: str,
    ) -> None:
        if self.fail_on_deactivate is not None:
            raise self.fail_on_deactivate
        key = ("/deactivate", idempotency_key)
        if key in self._by_key:
            return
        call = RecordedDeactivate(
            endpoint="/deactivate",
            imsi=imsi,
            reason=reason,
            idempotency_key=idempotency_key,
        )
        self.calls.append(call)
        self._by_key[key] = call

    def data(
        self,
        imsi: str,
        *,
        mode: str,
        speed_ul_mbps: float | None,
        speed_dl_mbps: float | None,
        idempotency_key: str,
    ) -> None:
        if self.fail_on_data is not None:
            raise self.fail_on_data
        key = ("/data", idempotency_key)
        if key in self._by_key:
            return
        call = RecordedData(
            endpoint="/data",
            imsi=imsi,
            mode=mode,
            speed_ul_mbps=speed_ul_mbps,
            speed_dl_mbps=speed_dl_mbps,
            idempotency_key=idempotency_key,
        )
        self.calls.append(call)
        self._by_key[key] = call

    def get_line(self, imsi: str) -> dict[str, object]:
        return {"status": "active", "imsi": imsi}


@dataclass
class FakePaidPlan:
    """Stands in for BSS: money's answer to "has this line paid for data?"."""

    paid: bool = True

    def has_paid_allowance(self, line_id: int, now: object) -> bool:
        return self.paid
