"""The call_record migration: it builds the model, its checks bite, and it will not drop calls."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db import Base
from app.models import CallRecordModel  # noqa: F401  (registers the table on Base.metadata)

VERSIONS = Path(__file__).resolve().parents[3] / "services/app/migrations/versions"
FILE = next(VERSIONS.glob("*_a7c3e1f9b2d4_meter_call_records.py"))


def _load():
    spec = importlib.util.spec_from_file_location("call_record_migration", FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = _load()
INSERT = (
    "INSERT INTO call_record (call_id, from_msisdn, to_msisdn, started_at, answered_at, "
    "ended_at, end_reason) VALUES (:id, '2340000000001', '2340000000002', "
    "'2026-11-03 10:00:00', :answered, '2026-11-03 10:01:00', :reason)"
)


@pytest.fixture
def engine():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
    return engine


def run(engine, **params) -> None:
    with engine.begin() as conn:
        conn.execute(text(INSERT), params)


def test_it_follows_the_last_migration_and_nothing_follows_it_yet() -> None:
    assert migration.down_revision == "dd286ac07496" and migration.revision == "a7c3e1f9b2d4"
    heads = {f.stem for f in VERSIONS.glob("*.py")}
    assert not [h for h in heads if "a7c3e1f9b2d4" in h and h != FILE.stem]


def test_the_table_has_the_columns_the_constraints_and_the_indexes_of_the_model(engine) -> None:
    inspector = inspect(engine)
    table = Base.metadata.tables["call_record"]
    assert {c["name"] for c in inspector.get_columns("call_record")} == {
        c.name for c in table.columns
    }
    made = {c["name"] for c in inspector.get_check_constraints("call_record")}
    assert made == {c.name for c in table.constraints if c.name and c.name.startswith("ck_")}
    assert {i["name"] for i in inspector.get_indexes("call_record")} == {
        i.name for i in table.indexes
    }
    assert {u["name"] for u in inspector.get_unique_constraints("call_record")} == {
        "uq_call_record_call_id"
    }


def test_a_good_call_goes_in_and_the_checks_refuse_bad_ones(engine) -> None:
    run(engine, id="a", answered="2026-11-03 10:00:05", reason="completed")
    run(engine, id="b", answered=None, reason="declined")
    for bad in (
        dict(id="c", answered="2026-11-03 10:00:05", reason="busy"),  # not an end reason
        dict(id="d", answered=None, reason="completed"),  # completed but never answered
        dict(id="e", answered="2026-11-03 10:00:05", reason="failed"),  # answered but not completed
        dict(
            id="f", answered="2026-11-03 09:00:00", reason="completed"
        ),  # answered before the call began
        dict(id="a", answered=None, reason="declined"),  # the same call_id again
    ):
        with pytest.raises(IntegrityError):
            run(engine, **bad)


def test_it_will_not_drop_the_table_while_it_holds_calls_and_will_when_it_is_empty(engine) -> None:
    run(engine, id="a", answered="2026-11-03 10:00:05", reason="completed")
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        with pytest.raises(RuntimeError, match="refusing to drop"):
            migration.downgrade()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM call_record"))
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        migration.downgrade()
    assert "call_record" not in inspect(engine).get_table_names()
