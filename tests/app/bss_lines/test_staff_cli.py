"""Tests for the staff account command."""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.bss_lines import staff_cli
from app.bss_lines.repositories.desk_sql import SqlStaffRepository
from app.bss_lines.services.staff_auth import sign_in
from app.db import Base
from tests.app.bss_lines.desk_helpers import utc

PASSWORD = "a synthetic long password"


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[sessionmaker]:
    url = f"sqlite:///{tmp_path / 'cli.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr("common.passwords._N", 2**10)
    yield sessionmaker(engine, expire_on_commit=False)


def run(monkeypatch: pytest.MonkeyPatch, *argv: str, stdin: str = PASSWORD + "\n") -> int:
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    return staff_cli.main(list(argv))


def can_sign_in(database: sessionmaker, email: str, password: str) -> bool:
    with database() as session, session.begin():
        return sign_in(SqlStaffRepository(session), email, password, utc(2026, 11, 2)) is not None


def test_create_makes_an_account_that_can_sign_in(
    database: sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    code = run(
        monkeypatch, "create", "--email", "a@example.test", "--name", "A", "--role", "admin",
        "--password-stdin",
    )  # fmt: skip
    assert code == 0 and can_sign_in(database, "a@example.test", PASSWORD)


def test_the_password_is_never_printed_or_stored(
    database: sessionmaker, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run(monkeypatch, "create", "--email", "a@example.test", "--name", "A", "--role", "agent",
        "--password-stdin")  # fmt: skip
    seen = capsys.readouterr()
    assert PASSWORD not in seen.out + seen.err
    with database() as session:
        stored = session.execute(text("SELECT password_hash FROM staff_user")).scalar_one()
    assert PASSWORD not in stored


def test_there_is_no_password_argument() -> None:
    with pytest.raises(SystemExit):
        staff_cli.main(["create", "--email", "a@b.cd", "--name", "n", "--role", "agent",
                        "--password", "x"])  # fmt: skip


def test_a_duplicate_a_weak_password_and_a_bad_email_are_refused(
    database: sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = ("create", "--name", "A", "--role", "agent", "--password-stdin")
    assert run(monkeypatch, *base, "--email", "a@example.test") == 0
    assert run(monkeypatch, *base, "--email", "A@Example.test") == 1
    assert run(monkeypatch, *base, "--email", "b@example.test", stdin="short\n") == 1
    assert run(monkeypatch, *base, "--email", "not-an-email") == 1


def test_reset_disable_enable_and_list(
    database: sessionmaker, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run(monkeypatch, "create", "--email", "a@example.test", "--name", "A", "--role", "agent",
        "--password-stdin")  # fmt: skip
    new = "a different long password"
    assert run(monkeypatch, "reset-password", "--email", "a@example.test", "--password-stdin",
               stdin=new + "\n") == 0  # fmt: skip
    assert can_sign_in(database, "a@example.test", new)
    assert not can_sign_in(database, "a@example.test", PASSWORD)
    assert run(monkeypatch, "disable", "--email", "a@example.test") == 0
    assert not can_sign_in(database, "a@example.test", new)
    assert run(monkeypatch, "enable", "--email", "a@example.test") == 0
    assert can_sign_in(database, "a@example.test", new)
    capsys.readouterr()
    assert run(monkeypatch, "list") == 0
    listing = capsys.readouterr().out
    assert listing == "1\tagent\tactive\ta@example.test\n"
    assert new not in listing and "scrypt" not in listing


def test_an_unknown_account_is_refused(
    database: sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert run(monkeypatch, "disable", "--email", "nobody@example.test") == 1
    assert run(monkeypatch, "reset-password", "--email", "nobody@example.test",
               "--password-stdin") == 1  # fmt: skip
