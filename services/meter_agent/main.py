"""Entry point for the RatelMeter agent (core-up data mode)."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from pathlib import Path
from types import FrameType

from common.logging import configure_logging, log_event
from common.timeutil import utc_epoch_now

from .agent import Agent, AgentConfig
from .assignments import HttpAssignmentCache
from .config import Settings
from .counters import CounterReader, NftablesCounterReader, SnapshotCounterReader
from .ingest import HttpMeterPoster
from .spool import Spool

log = logging.getLogger("ratel.meter.main")


def create_counter_reader(settings: Settings) -> CounterReader:
    """A recorded file if one is named (tests, replays); otherwise the live nftables counters.

    There is no fallback to an empty reader: if the counters cannot be read, the tick fails and is
    logged, and no usage is invented for that interval.
    """
    if settings.snapshot_path is not None:
        return SnapshotCounterReader(settings.snapshot_path)
    return NftablesCounterReader(
        nft_path=settings.nft_path,
        family=settings.nft_family,
        table=settings.nft_table,
        up_set=settings.nft_up_set,
        down_set=settings.nft_down_set,
        timeout_seconds=settings.nft_timeout_seconds,
    )


def create_agent(settings: Settings | None = None) -> Agent:
    # The two API keys come from the environment (METER_AGENT_*); there is no built-in default.
    settings = settings or Settings()  # type: ignore[call-arg]
    reader = create_counter_reader(settings)
    cache = HttpAssignmentCache(
        base_url=settings.ratel_link_base_url,
        api_key=settings.ratel_link_api_key,
    )
    poster = HttpMeterPoster(
        base_url=settings.meter_api_base_url,
        api_key=settings.api_key,
    )
    spool_path = settings.spool_dir
    try:
        spool = Spool(spool_path)
    except PermissionError:
        spool_path = Path.home() / ".local/share/ratel-meter/spool"
        spool = Spool(spool_path)

    config = AgentConfig(
        spool_dir=str(spool_path),
        interval_seconds=settings.interval_seconds,
    )
    return Agent(reader, cache, poster, spool, config)


def run_agent_loop(agent: Agent, interval_seconds: int = 300) -> None:
    running = True

    def handle_signal(sig: int, _frame: FrameType | None) -> None:
        nonlocal running
        log_event(log, logging.INFO, "meter.agent.stopping", signal=sig)
        running = False

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    log_event(log, logging.INFO, "meter.agent.started", interval=interval_seconds)

    while running:
        start_time = utc_epoch_now()
        try:
            agent.run_once()
        except Exception as exc:
            log_event(
                log,
                logging.ERROR,
                "meter.agent.tick_error",
                error_type=type(exc).__name__,
            )

        now = utc_epoch_now()
        # Compute sleep duration until next clock-aligned interval
        next_interval = ((start_time // interval_seconds) + 1) * interval_seconds
        sleep_secs = max(1, next_interval - now)

        # Sleep in small slices to respond promptly to shutdown signals
        sleep_until = time.time() + sleep_secs
        while running and time.time() < sleep_until:
            time.sleep(min(1.0, sleep_until - time.time()))

    log_event(log, logging.INFO, "meter.agent.stopped")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RatelMeter agent for core-up")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one measurement tick and exit",
    )
    parser.add_argument(
        "--mode",
        default="data",
        choices=["data", "call"],
        help="Agent mode (data on core-up, call on voice)",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    settings = Settings()  # type: ignore[call-arg]  # the keys come from the environment
    if args.mode:
        settings.mode = args.mode

    configure_logging(settings.log_level)

    agent = create_agent(settings)
    if args.once:
        agent.run_once()
        return 0

    run_agent_loop(agent, interval_seconds=settings.interval_seconds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
