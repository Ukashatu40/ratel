"""The live counter reader for core-up: it runs `nft` and reads the per-address counters.

One call, `nft -j list table <family> <table>`, returns both counter sets in one document, so the
upload and download figures always come from the same moment. The table itself is loaded at boot
by `deploy/core-up/ratel-meter.nft` (see deploy/core-up/README.md).

Any failure raises `CounterReadError`. It never returns an empty result for a problem: the agent
skips that interval, and the totals it already holds are untouched.
"""

from __future__ import annotations

import logging
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from common.logging import log_event
from common.timeutil import utc_epoch_now

from ..domain.records import Reading
from .errors import CounterUnavailableError
from .reader import DOWN_SET, UP_SET, parse_nftables_json

log = logging.getLogger("ratel.meter.counters")

FAMILIES = ("inet", "ip", "ip6")
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class NftablesCounterReader:
    def __init__(
        self,
        *,
        nft_path: Path = Path("/usr/sbin/nft"),
        family: str = "inet",
        table: str = "ratel_meter",
        up_set: str = UP_SET,
        down_set: str = DOWN_SET,
        timeout_seconds: float = 10.0,
        runner: Runner | None = None,
    ) -> None:
        if family not in FAMILIES:
            raise ValueError(f"nft family must be one of {FAMILIES}")
        for label, value in (("table", table), ("up set", up_set), ("down set", down_set)):
            if not _NAME.match(value):
                raise ValueError(f"nft {label} name must be letters, digits and underscores")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._argv = [str(nft_path), "-j", "list", "table", family, table]
        self._up_set, self._down_set = up_set, down_set
        self._timeout = timeout_seconds
        self._run: Runner = runner or subprocess.run

    def read(self) -> dict[str, Reading]:
        now = utc_epoch_now()
        try:
            # A fixed argument list, never a shell. Nothing here comes from a request.
            done: Any = self._run(
                self._argv, capture_output=True, text=True, timeout=self._timeout, check=False
            )
        except FileNotFoundError as exc:
            raise CounterUnavailableError("The nft executable was not found") from exc
        except subprocess.TimeoutExpired as exc:
            raise CounterUnavailableError("nft did not answer in time") from exc
        except OSError as exc:
            raise CounterUnavailableError("nft could not be started") from exc

        if done.returncode != 0:
            # The table is missing, or the agent may not read it. Never an empty reading.
            log_event(log, logging.ERROR, "meter.counters.nft_failed", exit_status=done.returncode)
            raise CounterUnavailableError(f"nft exited with status {done.returncode}")

        readings = parse_nftables_json(
            done.stdout, read_at=now, up_set=self._up_set, down_set=self._down_set
        )
        # The count only: addresses never go in a log line.
        log_event(log, logging.DEBUG, "meter.counters.read", address_count=len(readings))
        return readings
