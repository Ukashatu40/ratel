"""The voucher CLI: PINs go to one private file and nowhere else."""

from __future__ import annotations

import csv
import stat
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.bss_money.domain.pins import verify_pin
from app.bss_money.models.vouchers import Voucher
from app.bss_money.voucher_cli import main
from app.db import Base


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    url = f"sqlite+pysqlite:///{tmp_path / 'bss.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    monkeypatch.setenv("DATABASE_URL", url)
    return url


def _rows(url: str) -> list[Voucher]:
    engine = create_engine(url)
    with Session(engine) as session:
        rows = list(session.scalars(select(Voucher).order_by(Voucher.voucher_id)))
    engine.dispose()
    return rows


def _batch(tmp_path: Path, count: int = 3) -> list[str]:
    return [
        "create-batch",
        "--batch",
        "nov",
        "--count",
        str(count),
        "--value-kobo",
        "50000",
        "--out",
        str(tmp_path / "cards.csv"),
    ]


def test_create_batch_writes_the_cards_to_a_private_file_and_only_hashes_to_the_database(
    database: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(_batch(tmp_path)) == 0

    out = tmp_path / "cards.csv"
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    cards = list(csv.DictReader(out.open()))
    rows = _rows(database)
    assert len(cards) == len(rows) == 3
    for card, row in zip(cards, rows, strict=True):
        assert card["card_number"] == row.card_number
        assert verify_pin(card["pin"], row.pin_hash)
        assert card["pin"] not in row.pin_hash
        assert row.state == "requested"
    shown = capsys.readouterr()
    for card in cards:
        assert card["pin"] not in shown.out + shown.err  # never on the terminal


def test_create_batch_will_not_overwrite_a_file(
    database: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "cards.csv").write_text("precious")

    assert main(_batch(tmp_path)) == 2

    assert (tmp_path / "cards.csv").read_text() == "precious"
    assert _rows(database) == []


def test_a_bad_request_leaves_no_file_and_no_cards(database: str, tmp_path: Path) -> None:
    assert main(_batch(tmp_path, count=0)) == 1

    assert not (tmp_path / "cards.csv").exists()
    assert _rows(database) == []


def test_set_state_walks_a_batch_along_and_refuses_a_skip(
    database: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(_batch(tmp_path))

    assert main(["set-state", "--batch", "nov", "--to", "on_sale"]) == 1  # cannot skip
    assert main(["set-state", "--batch", "nov", "--to", "approved"]) == 0
    assert {r.state for r in _rows(database)} == {"approved"}
    assert main(["set-state", "--batch", "missing", "--to", "approved"]) == 1


def test_lock_stops_one_card(database: str, tmp_path: Path) -> None:
    main(_batch(tmp_path))

    assert main(["lock", "--voucher-id", "2"]) == 0
    assert [r.state for r in _rows(database)] == ["requested", "locked", "requested"]
    assert main(["lock", "--voucher-id", "2"]) == 1  # a locked card stays locked
    assert main(["lock", "--voucher-id", "99"]) == 1


def test_exit_2_when_the_database_cannot_be_reached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'missing' / 'x.db'}")
    assert main(["lock", "--voucher-id", "1"]) == 2
    assert "missing" not in capsys.readouterr().err
