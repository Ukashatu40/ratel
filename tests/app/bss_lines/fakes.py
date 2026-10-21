"""In-memory RatelLinkClient for tests.

Records every call so we can assert "exactly one /activate".
A repeat with the same key does not record a second call (mirrors what
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
