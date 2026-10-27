"""The 300-second RatelMeter data-agent loop (W2-09).

Reads counters, refreshes the address-to-IMSI cache, builds records,
posts them, and spools on failure. The reader, cache and poster are
protocols, so this module is testable with fakes while W2-08, W2-03 and
W2-12 are still open.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from common.logging import log_event
from common.timeutil import interval_start, utc_epoch_now

from .assignments import AssignmentCache
from .counters import CounterReader
from .domain.intervals import INTERVAL_SECONDS, build_record, increase
from .domain.records import Increase, Reading, UsageRecord
from .ingest import MeterPoster
from .spool import Spool

log = logging.getLogger("ratel.meter.agent")


@dataclass(frozen=True, slots=True)
class AgentConfig:
    spool_dir: str
    interval_seconds: int = INTERVAL_SECONDS


class Agent:
    """One pass: read, refresh, build, post, spool on failure."""

    def __init__(
        self,
        reader: CounterReader,
        cache: AssignmentCache,
        poster: MeterPoster,
        spool: Spool,
        config: AgentConfig,
    ) -> None:
        self._reader = reader
        self._cache = cache
        self._poster = poster
        self._spool = spool
        self._config = config
        self._last: dict[str, Reading] = {}

    def run_once(self, now: int | None = None) -> None:
        """Run one interval's work.

        Intended to be called every INTERVAL_SECONDS, aligned to the
        clock. The schedule itself is out of scope for W2-09's skeleton;
        see the ticket's runbook note.
        """
        current_time = now if now is not None else utc_epoch_now()

        # Refresh first: readings kept from an earlier tick can only be attributed to a line
        # once the map is fresh.
        cache_ok = self._refresh_cache()

        # Drain anything spooled in an earlier tick first. A file
        # spooled later in *this* tick is not retried until the next
        # tick, which keeps this call's behavior unambiguous.
        self._spool.replay(lambda batch: self._deliver(batch, cache_ok))

        readings = self._reader.read()

        if not cache_ok:
            # The address-to-IMSI map could not be refreshed, so nobody can say whose bytes
            # these are yet. Keep the raw readings on disk and attribute them once a refresh
            # works. Never send raw readings to the API, which expects usage records only.
            raw: list[dict[str, object]] = []
            for ue_ip, current in readings.items():
                delta = increase(self._last.get(ue_ip), current)
                self._last[ue_ip] = current
                if delta.bytes_up == 0 and delta.bytes_down == 0:
                    continue
                raw.append(
                    {
                        "ue_ip": ue_ip,
                        "bytes_up": delta.bytes_up,
                        "bytes_down": delta.bytes_down,
                        "read_at": current.read_at,
                    }
                )
            if raw:
                name = (
                    f"raw-{interval_start(current_time, self._config.interval_seconds):010d}.json"
                )
                self._spool.spool(name, raw)
            return

        batch: list[dict[str, object]] = []
        unmapped = _Unmapped()
        for ue_ip, current in readings.items():
            previous = self._last.get(ue_ip)
            delta = increase(previous, current)
            self._last[ue_ip] = current

            imsi = self._cache.imsi_for(ue_ip)
            if imsi is None:
                # Not a line we know about; skip it, and say so (counts only, no address).
                unmapped.add(delta.bytes_up, delta.bytes_down)
                continue

            record = build_record(imsi, current_time, delta)
            if record is None:
                # Zero-byte interval: no record.
                continue
            batch.append(_as_batch_item(record))
        unmapped.report()

        if not batch:
            return

        if not self._poster(batch):
            # API unreachable: spool and try later.
            name = f"{interval_start(current_time, self._config.interval_seconds):010d}.json"
            self._spool.spool(name, batch)

    def _refresh_cache(self) -> bool:
        """True when the map is fresh. A cache that raises, or says nothing, counts as failed."""
        try:
            return self._cache.refresh() is True
        except Exception:
            return False

    def _deliver(self, batch: object, cache_ok: bool) -> bool:
        """Send one spooled batch. Raw readings are attributed to lines first."""
        if not _is_raw(batch):
            return self._poster(batch)
        if not cache_ok:
            return False  # keep it until the map can be refreshed
        assert isinstance(batch, list)
        unmapped = _Unmapped()
        records: list[dict[str, object]] = []
        for item in batch:
            imsi = self._cache.imsi_for(item["ue_ip"])
            up, down = item["bytes_up"], item["bytes_down"]
            if imsi is None:
                unmapped.add(up, down)
                continue
            record = build_record(imsi, item["read_at"], Increase(up, down))
            if record is not None:
                records.append(_as_batch_item(record))
        unmapped.report()
        return self._poster(records) if records else True


def _as_batch_item(record: UsageRecord) -> dict[str, object]:
    return {
        "imsi": record.imsi,
        "period_start": record.period_start,
        "period_end": record.period_end,
        "bytes_up": record.bytes_up,
        "bytes_down": record.bytes_down,
    }


def _is_raw(batch: object) -> bool:
    """A spooled file of counter readings (see run_once), not of usage records."""
    return (
        isinstance(batch, list)
        and len(batch) > 0
        and all(
            isinstance(item, dict)
            and isinstance(item.get("ue_ip"), str)
            and isinstance(item.get("read_at"), int)
            and isinstance(item.get("bytes_up"), int)
            and isinstance(item.get("bytes_down"), int)
            for item in batch
        )
    )


class _Unmapped:
    """Usage from addresses that no line owns. Logged as counts: no address, no IMSI."""

    def __init__(self) -> None:
        self._addresses = 0
        self._up = 0
        self._down = 0

    def add(self, bytes_up: int, bytes_down: int) -> None:
        if bytes_up or bytes_down:
            self._addresses += 1
            self._up += bytes_up
            self._down += bytes_down

    def report(self) -> None:
        if self._addresses:
            log_event(
                log,
                logging.WARNING,
                "meter.agent.unmapped_usage",
                addresses=self._addresses,
                bytes_up=self._up,
                bytes_down=self._down,
            )
