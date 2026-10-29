"""Compare our stored usage with the network's own counters for a window (M-28).

    python -m app.meter_api.reconcile_cli --from EPOCH --to EPOCH --network-totals FILE
        [--tolerance-bps 100]

FILE has one `imsi,bytes` line per SIM: what the network counted in the window (the network team
supplies it). The window is `[from, to)` in Unix epoch seconds; use 300-second boundaries, because
a record covers a whole interval.

Exit 0: every line is within the tolerance. Exit 1: at least one differs, or is on one side only
(listed, with the IMSI masked). Exit 2: the check could not run (bad file, bad window, database).
Nothing is changed. An entry point: it builds the session and hands it to the service.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.db import make_engine, session_factory
from app.meter_api.repositories.sql import SqlUsageRepository
from app.meter_api.services.reconcile import (
    DEFAULT_TOLERANCE_BPS,
    BadNetworkTotals,
    Report,
    parse_network_totals,
    reconcile,
)
from common.logging import configure_logging, log_event
from common.timeutil import from_epoch

log = logging.getLogger("ratel.meter.reconcile")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="reconcile_cli", description=__doc__)
    parser.add_argument("--from", dest="start", type=int, required=True)
    parser.add_argument("--to", dest="end", type=int, required=True)
    parser.add_argument("--network-totals", type=Path, required=True)
    parser.add_argument("--tolerance-bps", type=int, default=DEFAULT_TOLERANCE_BPS)
    return parser


def _print(report: Report, tolerance_bps: int) -> None:
    out = sys.stdout.write
    out(
        f"compared {report.compared} line(s): {report.within} within "
        f"{tolerance_bps / 100:g}%, {len(report.flagged)} flagged\n"
    )
    out(f"total bytes: ours {report.our_total}, network {report.network_total}\n")
    for item in report.flagged:
        ours = "none" if item.ours is None else str(item.ours)
        theirs = "none" if item.network is None else str(item.network)
        gap = "" if item.percent is None else f" ({item.percent:.2f}% off)"
        out(f"  {item.masked_imsi}: ours {ours}, network {theirs}{gap}\n")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = Settings()
    configure_logging(settings.log_level, stream=sys.stderr)
    try:
        network = parse_network_totals(args.network_totals.read_text())
    except (OSError, BadNetworkTotals) as exc:
        # The message names a line number, never a value; an OSError text names a path only.
        sys.stderr.write(f"cannot read the network totals: {exc}\n")
        return 2
    engine = make_engine(settings.database_url.get_secret_value())
    try:
        with session_factory(engine)() as session:
            report = reconcile(
                SqlUsageRepository(session),
                network,
                from_epoch(args.start),
                from_epoch(args.end),
                args.tolerance_bps,
            )
    except ValueError as exc:
        sys.stderr.write(f"cannot compare: {exc}\n")
        return 2
    except SQLAlchemyError as exc:
        # Type only: a driver message can carry the database host and user.
        log_event(log, logging.ERROR, "reconcile.failed", exc_type=type(exc).__name__)
        return 2
    finally:
        engine.dispose()
    _print(report, args.tolerance_bps)
    log_event(
        log,
        logging.INFO,
        "reconcile.done",
        compared=report.compared,
        flagged=len(report.flagged),
        our_total=report.our_total,
        network_total=report.network_total,
    )
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
