"""Operator tool for the plans, bundles and wallets the lab and the demo need.

    python -m app.bss_money.ops_cli plan add --name N --price-kobo P --validity-days D \
        --data-bytes B --up-mbps U --down-mbps W --on-exhaustion slow \
        --slow-up-mbps u --slow-down-mbps w
    python -m app.bss_money.ops_cli plan list
    python -m app.bss_money.ops_cli plan retire --plan-id ID
    python -m app.bss_money.ops_cli bundle add --name N --price-kobo P --validity-days D \
        --data-bytes B
    python -m app.bss_money.ops_cli bundle list
    python -m app.bss_money.ops_cli bundle retire --bundle-id ID
    python -m app.bss_money.ops_cli wallet show --line-id ID
    python -m app.bss_money.ops_cli wallet credit --line-id ID --amount-kobo K \
        --reference TEXT --operator NAME
    python -m app.bss_money.ops_cli buy --line-id ID (--plan-id ID | --bundle-id ID) \
        --reference TEXT

A stopgap until RatelBSS has its own staff API (M-26): the plan and bundle rules are checked by the
same code RatelBSS uses, and `buy` is the service the rating job renews with. **`wallet credit`
puts money in a wallet by hand.** The ledger is append-only, so every credit is permanent; the
reference is recorded as `manual:<text>`, the operator and the amount are logged, and it is meant
for the lab and rehearsals, not as the way customers pay (vouchers and the gateway are).

Exit 0: done. Exit 1: refused (bad input, no such line or offer, not enough money). Exit 2: could
not run (the database did not answer).
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.bss_lines.models.lines import Bundle as BundleRow
from app.bss_lines.models.lines import Plan as PlanRow
from app.bss_money.domain.entries import InvalidPosting, new_posting
from app.bss_money.domain.plans import Bundle, OnExhaustion, Plan
from app.bss_money.domain.purchase import OfferKind
from app.bss_money.repositories.ports import PurchaseRepositories
from app.bss_money.repositories.sql import SqlLedgerRepository, SqlPurchaseRepository
from app.bss_money.services.ledger import post_entry
from app.bss_money.services.purchase import PurchaseError, buy_offer
from app.config import Settings
from app.db import make_engine, session_factory
from common.logging import configure_logging, log_event

log = logging.getLogger("ratel.bss.money.ops")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ops_cli")
    top = parser.add_subparsers(dest="group", required=True)

    plan = top.add_parser("plan").add_subparsers(dest="action", required=True)
    add_plan = plan.add_parser("add")
    for flag, kind in (
        ("--name", str),
        ("--price-kobo", int),
        ("--validity-days", int),
        ("--data-bytes", int),
        ("--up-mbps", float),
        ("--down-mbps", float),
    ):
        add_plan.add_argument(flag, type=kind, required=True)
    add_plan.add_argument("--on-exhaustion", choices=[e.value for e in OnExhaustion], required=True)
    add_plan.add_argument("--slow-up-mbps", type=float)
    add_plan.add_argument("--slow-down-mbps", type=float)
    add_plan.add_argument("--channels", default="data")
    plan.add_parser("list")
    retire = plan.add_parser("retire")
    retire.add_argument("--plan-id", type=int, required=True)

    bundle = top.add_parser("bundle").add_subparsers(dest="action", required=True)
    add_bundle = bundle.add_parser("add")
    for flag, kind in (
        ("--name", str),
        ("--price-kobo", int),
        ("--validity-days", int),
        ("--data-bytes", int),
    ):
        add_bundle.add_argument(flag, type=kind, required=True)
    add_bundle.add_argument("--channels", default="data")
    bundle.add_parser("list")
    retire_bundle = bundle.add_parser("retire")
    retire_bundle.add_argument("--bundle-id", type=int, required=True)

    wallet = top.add_parser("wallet").add_subparsers(dest="action", required=True)
    show = wallet.add_parser("show")
    show.add_argument("--line-id", type=int, required=True)
    credit = wallet.add_parser("credit")
    credit.add_argument("--line-id", type=int, required=True)
    credit.add_argument("--amount-kobo", type=int, required=True)
    credit.add_argument("--reference", required=True)
    credit.add_argument("--operator", required=True)

    buy = top.add_parser("buy")
    buy.add_argument("--line-id", type=int, required=True)
    which = buy.add_mutually_exclusive_group(required=True)
    which.add_argument("--plan-id", type=int)
    which.add_argument("--bundle-id", type=int)
    buy.add_argument("--reference", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = Settings()
    configure_logging(settings.log_level, stream=sys.stderr)
    engine = make_engine(settings.database_url.get_secret_value())
    sessions = session_factory(engine)

    @contextmanager
    def purchase_scope() -> Iterator[PurchaseRepositories]:
        with sessions() as session, session.begin():
            yield PurchaseRepositories(SqlPurchaseRepository(session), SqlLedgerRepository(session))

    try:
        with sessions() as session, session.begin():
            return _run(args, session, purchase_scope, settings.vat_rate_bps)
    except (ValueError, PurchaseError, InvalidPosting) as exc:
        sys.stderr.write(f"refused: {exc}\n")
        return 1
    except SQLAlchemyError as exc:
        # Type only: a driver message can carry the database host and user.
        log_event(log, logging.ERROR, "ops.cli_failed", exc_type=type(exc).__name__)
        return 2
    finally:
        engine.dispose()


def _run(args: argparse.Namespace, session: Session, purchase_scope, vat_rate_bps: int) -> int:  # type: ignore[no-untyped-def]
    if args.group == "plan":
        return _plan(args, session)
    if args.group == "bundle":
        return _bundle(args, session)
    if args.group == "wallet":
        return _wallet(args, session)
    kind, offer_id = (
        (OfferKind.PLAN, args.plan_id) if args.plan_id else (OfferKind.BUNDLE, args.bundle_id)
    )
    result = buy_offer(
        purchase_scope,
        line_id=args.line_id,
        kind=kind,
        offer_id=offer_id,
        reference=f"manual:{args.reference}",
        now=datetime.now(UTC),
        vat_rate_bps=vat_rate_bps,
    )
    note = " (this reference was already used: nothing changed)" if result.replayed else ""
    sys.stdout.write(
        f"bought for {result.price_kobo} kobo (VAT {result.vat_kobo}); "
        f"balance {result.balance_kobo}{note}\n"
    )
    return 0


def _plan(args: argparse.Namespace, session: Session) -> int:
    if args.action == "list":
        for row in session.scalars(select(PlanRow).order_by(PlanRow.plan_id)):
            sys.stdout.write(
                f"{row.plan_id}\t{row.name}\t{row.price_kobo} kobo\t{row.validity_days} d\t"
                f"{row.data_bytes} B\t{row.on_exhaustion}\t{row.state}\n"
            )
        return 0
    if args.action == "retire":
        existing = session.get(PlanRow, args.plan_id)
        if existing is None:
            raise ValueError("no such plan")
        existing.state = "retired"
        return 0
    # Validate with the rules RatelBSS uses (the id is a placeholder: the database assigns it).
    Plan(
        plan_id=1,
        name=args.name,
        price_kobo=args.price_kobo,
        validity_days=args.validity_days,
        data_bytes=args.data_bytes,
        speed_ul_mbps=args.up_mbps,
        speed_dl_mbps=args.down_mbps,
        channels=tuple(c for c in args.channels.split(",") if c),
        on_exhaustion=OnExhaustion(args.on_exhaustion),
        slow_ul_mbps=args.slow_up_mbps,
        slow_dl_mbps=args.slow_down_mbps,
    )
    row = PlanRow(
        name=args.name,
        price_kobo=args.price_kobo,
        validity_days=args.validity_days,
        data_bytes=args.data_bytes,
        speed_ul_mbps=args.up_mbps,
        speed_dl_mbps=args.down_mbps,
        slow_ul_mbps=args.slow_up_mbps,
        slow_dl_mbps=args.slow_down_mbps,
        channels=args.channels,
        on_exhaustion=args.on_exhaustion,
        state="on_sale",
    )
    session.add(row)
    session.flush()
    sys.stdout.write(f"plan {row.plan_id} added\n")
    return 0


def _bundle(args: argparse.Namespace, session: Session) -> int:
    if args.action == "list":
        for row in session.scalars(select(BundleRow).order_by(BundleRow.bundle_id)):
            sys.stdout.write(
                f"{row.bundle_id}\t{row.name}\t{row.price_kobo} kobo\t"
                f"{row.validity_days} d\t{row.data_bytes} B\t{row.state}\n"
            )
        return 0
    if args.action == "retire":
        existing = session.get(BundleRow, args.bundle_id)
        if existing is None:
            raise ValueError("no such bundle")
        existing.state = "retired"
        return 0
    Bundle(
        bundle_id=1,
        name=args.name,
        price_kobo=args.price_kobo,
        validity_days=args.validity_days,
        data_bytes=args.data_bytes,
        channels=tuple(c for c in args.channels.split(",") if c),
    )
    row = BundleRow(
        name=args.name,
        price_kobo=args.price_kobo,
        validity_days=args.validity_days,
        data_bytes=args.data_bytes,
        channels=args.channels,
    )
    session.add(row)
    session.flush()
    sys.stdout.write(f"bundle {row.bundle_id} added\n")
    return 0


def _wallet(args: argparse.Namespace, session: Session) -> int:
    ledger = SqlLedgerRepository(session)
    if args.action == "show":
        balance = ledger.balance(args.line_id)
        sys.stdout.write("no wallet yet\n" if balance is None else f"{balance} kobo\n")
        return 0
    if args.amount_kobo <= 0:
        raise ValueError("a credit must be a positive amount")
    posting = new_posting(args.line_id, args.amount_kobo, "top_up", f"manual:{args.reference}")
    result = post_entry(ledger, posting)
    log_event(
        log,
        logging.WARNING,
        "ops.wallet_credit",
        line_id=args.line_id,
        amount_kobo=args.amount_kobo,
        operator=args.operator,
        replayed=result.replayed,
    )
    note = " (this reference was already used)" if result.replayed else ""
    sys.stdout.write(f"balance {result.balance_kobo} kobo{note}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
