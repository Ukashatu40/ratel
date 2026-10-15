"""The 300-second RatelMeter data-agent loop (W2-09).

Reads counters, refreshes the address-to-IMSI cache, builds records,
posts them, and spools on failure. The reader, cache and poster are
protocols, so this module is testable with fakes while W2-08, W2-03 and
W2-12 are still open.
"""

from __future__ import annotations

from dataclasses import dataclass

from common.timeutil import interval_start, utc_epoch_now

from .assignments import AssignmentCache
from .counters import CounterReader
from .domain.intervals import INTERVAL_SECONDS, build_record, increase
from .domain.records import Reading
from .ingest import MeterPoster
from .spool import Spool


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

    def run_once(self) -> None:
        """Run one interval's work.

        Intended to be called every INTERVAL_SECONDS, aligned to the
        clock. The schedule itself is out of scope for W2-09's skeleton;
        see the ticket's runbook note.
        """
        # Drain anything spooled in an earlier tick first. A file
        # spooled later in *this* tick is not retried until the next
        # tick, which keeps this call's behavior unambiguous.
        self._spool.replay(self._poster)

        now = utc_epoch_now()
        readings = self._reader.read()

        cache_ok = True
        try:
            self._cache.refresh()
        except Exception:
            cache_ok = False

        if not cache_ok:
            # The address-to-IMSI map is stale. Spool the raw readings;
            # resolve IMSIs on replay. Never send raw readings to the
            # API, which expects usage records only.
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
                name = f"raw-{interval_start(now, self._config.interval_seconds):010d}.json"
                self._spool.spool(name, raw)
            return

        batch: list[dict[str, object]] = []
        for ue_ip, current in readings.items():
            previous = self._last.get(ue_ip)
            delta = increase(previous, current)
            self._last[ue_ip] = current

            imsi = self._cache.imsi_for(ue_ip)
            if imsi is None:
                # Not a line we know about; skip it.
                continue

            record = build_record(imsi, now, delta)
            if record is None:
                # Zero-byte interval: no record.
                continue
            batch.append(
                {
                    "imsi": record.imsi,
                    "period_start": record.period_start,
                    "period_end": record.period_end,
                    "bytes_up": record.bytes_up,
                    "bytes_down": record.bytes_down,
                }
            )

        if not batch:
            return

        if not self._poster(batch):
            # API unreachable: spool and try later.
            name = f"{interval_start(now, self._config.interval_seconds):010d}.json"
            self._spool.spool(name, batch)
