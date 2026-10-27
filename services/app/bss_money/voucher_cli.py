"""Make and manage voucher batches. Run by a person on bss-app, never by a timer.

    python -m app.bss_money.voucher_cli create-batch \
        --batch NAME --count N --value-kobo K --out FILE
    python -m app.bss_money.voucher_cli set-state --batch NAME --to approved
    python -m app.bss_money.voucher_cli lock --voucher-id ID

`create-batch` writes the card numbers and PINs to FILE (a new file, readable only by you) and
prints nothing but how many cards it made. **That file is the only place the PINs ever exist.**
Hand it to the printer, then delete it. It is written before the cards are committed, so a crash
can leave a file of PINs for cards that do not exist, never cards whose PINs are lost.

Exit 0: done. Exit 1: refused (unknown batch, a card that cannot make that move, bad input).
Exit 2: could not run (the database did not answer, or FILE already exists).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from app.bss_money.domain.vouchers import InvalidVoucherTransition, VoucherState
from app.bss_money.repositories.sql import SqlVoucherRepository
from app.bss_money.services.vouchers import create_batch, set_batch_state, set_card_state
from app.config import Settings
from app.db import make_engine, session_factory
from common.logging import configure_logging, log_event

log = logging.getLogger("ratel.bss.money.vouchers")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="voucher_cli")
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("create-batch")
    make.add_argument("--batch", required=True)
    make.add_argument("--count", type=int, required=True)
    make.add_argument("--value-kobo", type=int, required=True)
    make.add_argument("--out", type=Path, required=True)
    move = commands.add_parser("set-state")
    move.add_argument("--batch", required=True)
    move.add_argument("--to", required=True, choices=[s.value for s in VoucherState])
    lock = commands.add_parser("lock")
    lock.add_argument("--voucher-id", type=int, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = Settings()
    configure_logging(settings.log_level, stream=sys.stderr)
    engine = make_engine(settings.database_url.get_secret_value())
    try:
        with session_factory(engine)() as session, session.begin():
            vouchers = SqlVoucherRepository(session)
            if args.command == "create-batch":
                return _create(vouchers, args)
            if args.command == "set-state":
                count = set_batch_state(vouchers, args.batch, VoucherState(args.to))
                sys.stderr.write(f"{count} card(s) now {args.to}\n")
                return 0
            set_card_state(vouchers, args.voucher_id, VoucherState.LOCKED)
            sys.stderr.write("card locked\n")
            return 0
    except (InvalidVoucherTransition, LookupError, ValueError) as exc:
        sys.stderr.write(f"refused: {exc}\n")
        return 1
    except SQLAlchemyError as exc:
        # Type only: a driver message can carry the database host and user.
        log_event(log, logging.ERROR, "voucher.cli_failed", exc_type=type(exc).__name__)
        return 2
    finally:
        engine.dispose()


def _create(vouchers: SqlVoucherRepository, args: argparse.Namespace) -> int:
    try:
        descriptor = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        sys.stderr.write("the output file already exists; choose a new name\n")
        return 2
    try:
        cards = create_batch(
            vouchers, batch=args.batch, count=args.count, face_value_kobo=args.value_kobo
        )
        with os.fdopen(descriptor, "w") as out:
            out.write("card_number,pin\n")
            out.writelines(f"{card.card_number},{card.pin}\n" for card in cards)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        args.out.unlink(missing_ok=True)  # nothing was committed: do not leave PINs behind
        raise
    sys.stderr.write(f"{len(cards)} card(s) made; the PINs are in the output file only\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
