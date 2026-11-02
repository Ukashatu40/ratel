"""The stock command: safe to repeat, all or nothing, and it prints no identifier."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.bss_lines import stock_cli
from app.bss_lines.models.lines import Number, Sim
from app.db import Base

SIMS = (
    "iccid,imsi,batch\n"
    "8923400000000012345,621000000000150,LAB-1\n"
    "8923400000000012346,621000000000151,LAB-1\n"
)
NUMBERS = "msisdn\n2347000000150\n2347000000151\n"
IDENTIFIERS = ("8923400000000012345", "621000000000150", "2347000000150")


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[sessionmaker]:
    url = f"sqlite:///{tmp_path / 'stock.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("DATABASE_URL", url)
    yield sessionmaker(engine, expire_on_commit=False)


def file(tmp_path: Path, content: str) -> str:
    path = tmp_path / "in.csv"
    path.write_text(content)
    return str(path)


def counts(database: sessionmaker) -> tuple[int, int]:
    with database() as s:
        return s.scalar(select(func.count()).select_from(Sim)) or 0, s.scalar(
            select(func.count()).select_from(Number)
        ) or 0


def test_sims_and_numbers_go_into_stock_free_to_sell(
    database: sessionmaker, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert stock_cli.main(["add-sims", "--file", file(tmp_path, SIMS)]) == 0
    assert stock_cli.main(["add-numbers", "--file", file(tmp_path, NUMBERS)]) == 0
    assert counts(database) == (2, 2)
    with database() as s:
        assert {x.state for x in s.scalars(select(Sim))} == {"in_stock"}
        assert {x.state for x in s.scalars(select(Number))} == {"available"}
    err = capsys.readouterr().err
    assert "added 2 SIMs, skipped 0" in err and "added 2 numbers, skipped 0" in err


def test_loading_the_same_file_again_changes_nothing(
    database: sessionmaker, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = file(tmp_path, SIMS)
    assert stock_cli.main(["add-sims", "--file", path]) == 0
    capsys.readouterr()
    assert stock_cli.main(["add-sims", "--file", path]) == 0
    assert counts(database) == (2, 0)
    assert "added 0 SIMs, skipped 2" in capsys.readouterr().err


def test_a_clash_with_stock_loads_nothing(
    database: sessionmaker, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert stock_cli.main(["add-sims", "--file", file(tmp_path, SIMS)]) == 0
    capsys.readouterr()
    # The same ICCID with another IMSI, after a fresh SIM: the fresh one must not be loaded either.
    clash = (
        "iccid,imsi,batch\n"
        "8923400000000012399,621000000000199,LAB-2\n"
        "8923400000000012345,621000000000777,LAB-2\n"
    )
    assert stock_cli.main(["add-sims", "--file", file(tmp_path, clash)]) == 1
    assert counts(database) == (2, 0)
    assert "nothing was loaded" in capsys.readouterr().err


def test_a_file_with_keys_is_refused_and_nothing_is_loaded(
    database: sessionmaker, tmp_path: Path
) -> None:
    keyed = "iccid,imsi,ki,opc,batch\n8923400000000012345,621000000000150,TEST,TEST,LAB-1\n"
    assert stock_cli.main(["add-sims", "--file", file(tmp_path, keyed)]) == 1
    assert counts(database) == (0, 0)


def test_a_missing_file_is_refused(database: sessionmaker, tmp_path: Path) -> None:
    assert stock_cli.main(["add-sims", "--file", str(tmp_path / "nope.csv")]) == 1


def test_summary_counts_by_state_and_prints_no_identifier(
    database: sessionmaker, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stock_cli.main(["add-sims", "--file", file(tmp_path, SIMS)])
    stock_cli.main(["add-numbers", "--file", file(tmp_path, NUMBERS)])
    capsys.readouterr()
    assert stock_cli.main(["summary"]) == 0
    out = capsys.readouterr().out
    assert "sims: in_stock 2" in out and "numbers: available 2" in out


def test_nothing_the_command_writes_holds_an_identifier(
    database: sessionmaker, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stock_cli.main(["add-sims", "--file", file(tmp_path, SIMS)])
    stock_cli.main(
        [
            "add-sims",
            "--file",
            file(tmp_path, "iccid,imsi,batch\n8923400000000012345,short,LAB-1\n"),
        ]
    )
    stock_cli.main(["add-numbers", "--file", file(tmp_path, NUMBERS)])
    stock_cli.main(["summary"])
    captured = capsys.readouterr()
    for value in IDENTIFIERS:
        assert value not in captured.out and value not in captured.err
