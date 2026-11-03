"""The voice VM's call-record setup kept in Git: complete, consistent and free of secrets."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "network/voice/scscf-acc"
SQL = (FOLDER / "acc-columns.sql").read_text()
SNIPPETS = (FOLDER / "scscf-acc.cfg.snippets").read_text()
CHECK = FOLDER / "check-acc.sh"


def test_both_tables_get_the_three_columns_the_agent_reads() -> None:
    for table in ("acc", "missed_calls"):
        statement = re.search(rf"ALTER TABLE {table}\n(.*?);", SQL, re.S)
        assert statement is not None, table
        for column in ("from_user", "to_user", "start_ts"):
            assert f"ADD COLUMN {column}" in statement.group(1), (table, column)


def test_the_configuration_names_every_column_it_writes() -> None:
    extra = re.search(r'"db_extra", "([^"]+)"', SNIPPETS)
    assert extra is not None
    written = {pair.split("=")[0] for pair in extra.group(1).split(";")}
    assert written == {"from_user", "to_user", "start_ts"}
    for column in written:
        assert f"ADD COLUMN {column}" in SQL
    # The value the column takes is set where the request arrives.
    assert "$avp(acc_start) = $TS;" in SNIPPETS and "start_ts=$avp(acc_start)" in SNIPPETS


def test_the_flags_are_defined_before_they_are_used() -> None:
    assert SNIPPETS.index("#!define FLT_ACC 4") < SNIPPETS.index("setflag(FLT_ACC)")
    assert SNIPPETS.index('loadmodule "acc.so"') < SNIPPETS.index('modparam("acc"')


def test_the_check_matches_the_snippets_and_prints_no_data() -> None:
    text = CHECK.read_text()
    assert CHECK.stat().st_mode & 0o100, "check-acc.sh must be executable"
    for fragment in (
        "FLT_ACC 4",
        "FLT_ACCMISSED 8",
        'loadmodule "acc.so"',
        "start_ts=$avp(acc_start)",
    ):
        assert fragment in text, fragment
    assert "SELECT *" not in text and "select *" not in text.lower()
    assert "DB_URL" not in text and "mysql://" not in text


def test_nothing_in_the_folder_holds_a_database_url_a_password_or_an_address() -> None:
    for path in FOLDER.iterdir():
        body = path.read_text()
        assert not re.search(r"mysql://|password|passwd|BEGIN [A-Z ]*PRIVATE KEY", body, re.I), (
            path.name
        )
        assert not re.search(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", body), path.name
