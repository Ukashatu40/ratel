"""Put SIMs and numbers into RatelBSS's stock. Run by a person on bss-app, never by a timer.

    python -m app.bss_lines.stock_cli add-sims --file sims.csv
    python -m app.bss_lines.stock_cli add-numbers --file numbers.csv
    python -m app.bss_lines.stock_cli summary

The SIM file has the columns `iccid,imsi,batch` and nothing else; a column for a key is refused (BSS
never holds Ki or OPc, which live in RatelLink). The number file has one number per line in the
stored form (digits, international, no plus). Loading is all or nothing, and safe to repeat: what is
already in stock exactly as in the file is skipped. Nothing here prints an ICCID, an IMSI or a
number: only counts. Delete the files afterwards (`shred -u`): they hold identifiers.

Exit 0: done. Exit 1: refused (a bad file, a clash with stock). Exit 2: could not run (the database
did not answer).
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from app.bss_lines.domain.stock import parse_numbers, parse_sims
from app.bss_lines.repositories.stock_sql import SqlStockLoader, StockConflict
from app.config import Settings
from app.db import make_engine, session_factory
from common.logging import configure_logging, log_event

log = logging.getLogger("ratel.bss.lines.stock")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stock_cli")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("add-sims", "add-numbers"):
        commands.add_parser(name).add_argument("--file", type=Path, required=True)
    commands.add_parser("summary")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = Settings()
    configure_logging(settings.log_level, stream=sys.stderr)
    try:
        text = args.file.read_text(encoding="utf-8") if args.command != "summary" else ""
    except (OSError, UnicodeDecodeError):
        sys.stderr.write("refused: the file could not be read\n")
        return 1
    engine = make_engine(settings.database_url.get_secret_value())
    try:
        with session_factory(engine)() as session, session.begin():
            return _run(SqlStockLoader(session), args.command, text)
    except StockConflict:
        sys.stderr.write(
            "refused: a SIM in the file clashes with one in stock; nothing was loaded\n"
        )
        return 1
    except ValueError as exc:
        sys.stderr.write(f"refused: {exc}\n")
        return 1
    except SQLAlchemyError as exc:
        # Type only: a driver message can carry the database host and user.
        log_event(log, logging.ERROR, "stock.cli_failed", exc_type=type(exc).__name__)
        return 2
    finally:
        engine.dispose()


def _run(loader: SqlStockLoader, command: str, text: str) -> int:
    if command == "summary":
        for kind, states in loader.summary().items():
            line = ", ".join(f"{state} {n}" for state, n in sorted(states.items())) or "none"
            sys.stdout.write(f"{kind}: {line}\n")
        return 0
    if command == "add-sims":
        done, word = loader.add_sims(parse_sims(text)), "SIMs"
    else:
        done, word = loader.add_numbers(parse_numbers(text)), "numbers"
    sys.stderr.write(f"added {done.added} {word}, skipped {done.skipped} already in stock\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
