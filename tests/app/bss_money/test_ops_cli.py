"""The operator tool: plans, bundles, wallets and purchases for the lab and the demo."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.bss_lines.models.lines import Plan as PlanRow
from app.bss_money.models.allowance import AllowanceBucket
from app.bss_money.models.ledger import LedgerEntry
from app.bss_money.ops_cli import main
from app.db import Base
from tests.app.bss_money.rating_data import seed_line

PLAN = [
    "plan",
    "add",
    "--name",
    "Demo 100 KB",
    "--price-kobo",
    "100000",
    "--validity-days",
    "30",
    "--data-bytes",
    "100000",
    "--up-mbps",
    "5",
    "--down-mbps",
    "10",
    "--on-exhaustion",
    "slow",
    "--slow-up-mbps",
    "0.5",
    "--slow-down-mbps",
    "1",
]


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    url = f"sqlite+pysqlite:///{tmp_path / 'bss.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        seed_line(session)  # line 1, with its own plan (id 1)
    engine.dispose()
    monkeypatch.setenv("DATABASE_URL", url)
    return url


def _count(url: str, table: type) -> int:
    engine = create_engine(url)
    with Session(engine) as session:
        value = session.scalar(select(func.count()).select_from(table))
    engine.dispose()
    return value or 0


def test_a_plan_is_added_listed_and_retired(
    database: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(PLAN) == 0
    assert "plan 2 added" in capsys.readouterr().out

    assert main(["plan", "list"]) == 0
    listing = capsys.readouterr().out
    assert "Demo 100 KB\t100000 kobo\t30 d\t100000 B\tslow\ton_sale" in listing

    assert main(["plan", "retire", "--plan-id", "2"]) == 0
    main(["plan", "list"])
    assert "retired" in capsys.readouterr().out.splitlines()[-1]
    assert main(["plan", "retire", "--plan-id", "99"]) == 1


@pytest.mark.parametrize(
    "change",
    [
        ("--slow-up-mbps", None),  # a plan that slows needs both slow speeds
        ("--price-kobo", "-5"),
        ("--validity-days", "0"),
        ("--data-bytes", "0"),
        ("--up-mbps", "0"),
    ],
)
def test_a_plan_that_breaks_the_rules_is_refused_and_not_stored(
    database: str, change: tuple[str, str | None]
) -> None:
    argv = list(PLAN)
    flag, value = change
    index = argv.index(flag)
    if value is None:
        del argv[index : index + 2]
    else:
        argv[index + 1] = value

    assert main(argv) == 1
    assert _count(database, PlanRow) == 1  # only the seeded one


def test_a_plan_that_stops_cannot_carry_slow_speeds(database: str) -> None:
    argv = [a for a in PLAN]
    argv[argv.index("--on-exhaustion") + 1] = "stop"
    assert main(argv) == 1


def test_a_bundle_is_added_and_listed(database: str, capsys: pytest.CaptureFixture[str]) -> None:
    argv = [
        "bundle",
        "add",
        "--name",
        "Weekly",
        "--price-kobo",
        "30000",
        "--validity-days",
        "7",
        "--data-bytes",
        "5000",
    ]
    assert main(argv) == 0
    assert main(["bundle", "list"]) == 0
    assert "Weekly\t30000 kobo\t7 d\t5000 B" in capsys.readouterr().out
    argv[argv.index("--validity-days") + 1] = "0"
    assert main(argv) == 1


def test_crediting_a_wallet_buying_a_plan_and_reading_the_balance(
    database: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["wallet", "show", "--line-id", "1"]) == 0
    assert "no wallet yet" in capsys.readouterr().out

    credit = [
        "wallet",
        "credit",
        "--line-id",
        "1",
        "--amount-kobo",
        "250000",
        "--reference",
        "lab-1",
        "--operator",
        "ukashatu",
    ]
    assert main(credit) == 0
    assert main(credit) == 0  # the same reference again changes nothing
    out = capsys.readouterr().out
    assert "balance 250000 kobo" in out.splitlines()[0]
    assert "already used" in out.splitlines()[1]

    assert main(["buy", "--line-id", "1", "--plan-id", "1", "--reference", "first-plan"]) == 0
    assert "bought for 100000 kobo (VAT 6977); balance 150000" in capsys.readouterr().out
    assert _count(database, AllowanceBucket) == 1
    assert _count(database, LedgerEntry) == 3  # the credit, the purchase and its VAT


def test_what_cannot_be_credited_or_bought_is_refused(
    database: str, capsys: pytest.CaptureFixture[str]
) -> None:
    base = ["wallet", "credit", "--line-id", "1", "--reference", "x", "--operator", "o"]
    assert main([*base, "--amount-kobo", "0"]) == 1
    assert main([*base, "--amount-kobo", "-5"]) == 1
    assert main(["buy", "--line-id", "1", "--plan-id", "1", "--reference", "r"]) == 1  # no money
    assert "does not cover" in capsys.readouterr().err
    assert main(["buy", "--line-id", "99", "--plan-id", "1", "--reference", "r"]) == 1
    assert _count(database, LedgerEntry) == 0
    assert _count(database, AllowanceBucket) == 0


def test_exit_2_when_the_database_cannot_be_reached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'missing' / 'x.db'}")
    assert main(["plan", "list"]) == 2
    assert "missing" not in capsys.readouterr().err
