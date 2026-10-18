"""In-memory RatelLinkClient for tests.

Records every call so we can assert "exactly one /activate".
Honours the idempotency key: a repeat with the same key is a no-op.
Can be told to fail, for error-path tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RecordedActivate:
    imsi: str
    msisdn: str
    speed_ul_mbps: float
    speed_dl_mbps: float
    voice: bool
    idempotency_key: str


@dataclass
class FakeRatelLinkClient:
    calls: list[RecordedActivate] = field(default_factory=list)
    _by_key: dict[str, RecordedActivate] = field(default_factory=dict)
    fail_on_activate: Exception | None = None

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
        if idempotency_key in self._by_key:
            return
        call = RecordedActivate(
            imsi=imsi,
            msisdn=msisdn,
            speed_ul_mbps=speed_ul_mbps,
            speed_dl_mbps=speed_dl_mbps,
            voice=voice,
            idempotency_key=idempotency_key,
        )
        self.calls.append(call)
        self._by_key[idempotency_key] = call

    def get_line(self, imsi: str) -> dict:
        return {"status": "active", "imsi": imsi}
