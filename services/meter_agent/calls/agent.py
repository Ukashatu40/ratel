"""One pass of call mode: replay the spool, read new rows, join them, spool and post the done."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from common.logging import log_event
from common.timeutil import utc_epoch_now

from ..ingest import MeterPoster
from ..spool import Spool
from .assemble import assemble
from .source import CallSource
from .state import StateStore

log = logging.getLogger("ratel.meter.calls")

BATCH = 1000  # records per batch; the API takes up to 5,000


@dataclass(frozen=True, slots=True)
class CallAgentConfig:
    settle_seconds: int = 10
    open_max_seconds: int = 21_600


class CallAgent:
    def __init__(
        self,
        source: CallSource,
        poster: MeterPoster,
        spool: Spool,
        state: StateStore,
        config: CallAgentConfig | None = None,
    ) -> None:
        self._source = source
        self._poster = poster
        self._spool = spool
        self._state = state
        self._config = config or CallAgentConfig()
        self._sequence = 0

    def run_once(self, now: int | None = None) -> None:
        current = now if now is not None else utc_epoch_now()
        self._spool.replay(self._poster)  # what an earlier pass could not deliver, oldest first

        state = self._state.load()
        rows, skipped = self._source.fetch(
            state.acc_id, state.missed_id, self._config.settle_seconds
        )
        if skipped:
            log_event(log, logging.WARNING, "meter.calls.rows_skipped", count=skipped)
        done = assemble(
            rows,
            state.open_calls,
            now=current,
            open_max_seconds=self._config.open_max_seconds,
            acc_id=state.acc_id,
            missed_id=state.missed_id,
        )

        # Spool first, then move the watermark: a crash between the two posts the same calls again,
        # and the API keeps one row per Call-ID.
        for start in range(0, len(done.finished), BATCH):
            self._sequence += 1
            name = f"calls-{current:012d}-{self._sequence:04d}.json"
            self._spool.spool(name, {"records": done.finished[start : start + BATCH]})
        state.acc_id, state.missed_id, state.open_calls = (
            done.acc_id,
            done.missed_id,
            done.open_calls,
        )
        self._state.save(state)

        log_event(
            log,
            logging.INFO,
            "meter.calls.assembled",
            rows=len(rows),
            finished=len(done.finished),
            open=len(done.open_calls),
            orphan_byes=done.orphan_byes,
            stale_dropped=done.stale_dropped,
        )
        if done.stale_dropped:
            log_event(
                log, logging.WARNING, "meter.calls.open_calls_dropped", count=done.stale_dropped
            )
        self._spool.replay(self._poster)
