"""The stock guarantee: a SIM or number cannot be taken twice, even by simultaneous requests.

Build Plan, RatelBSS: lines, M-25 acceptance criterion.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.bss_lines.services.stock import AlreadyTaken, take_number, take_sim
from tests.app.bss_money.postgres import Database

pytestmark = pytest.mark.integration

ICCID = "8900000000000000001"
MSISDN = "2348000000001"


def _seed_sim(db: Database) -> None:
    with db.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO sim (iccid, imsi, batch, state) "
                "VALUES (:iccid, '621000000000001', 'b', 'in_stock')"
            ),
            {"iccid": ICCID},
        )


def _seed_number(db: Database) -> None:
    with db.engine.begin() as conn:
        conn.execute(
            text("INSERT INTO number (msisdn, state) VALUES (:msisdn, 'available')"),
            {"msisdn": MSISDN},
        )


def test_take_sim_marks_it_in_use(db: Database) -> None:
    _seed_sim(db)
    with Session(db.engine) as s, s.begin():
        taken = take_sim(s, ICCID)
    assert taken.iccid == ICCID
    assert db.scalar("SELECT state FROM sim WHERE iccid = :c", {"c": ICCID}) == "in_use"


def test_take_sim_twice_fails(db: Database) -> None:
    _seed_sim(db)
    with Session(db.engine) as s, s.begin():
        take_sim(s, ICCID)
    with pytest.raises(AlreadyTaken), Session(db.engine) as s, s.begin():
        take_sim(s, ICCID)


def test_take_sim_concurrently_has_one_winner(db: Database) -> None:
    _seed_sim(db)
    racers = 8
    barrier = threading.Barrier(racers)

    def attempt(_: int) -> bool:
        barrier.wait()
        with Session(db.engine) as s, s.begin():
            try:
                take_sim(s, ICCID)
                return True
            except AlreadyTaken:
                return False

    with ThreadPoolExecutor(max_workers=racers) as pool:
        results = [f.result() for f in [pool.submit(attempt, i) for i in range(racers)]]

    assert results.count(True) == 1
    assert results.count(False) == racers - 1


def test_take_number_concurrently_has_one_winner(db: Database) -> None:
    _seed_number(db)
    racers = 8
    barrier = threading.Barrier(racers)

    def attempt(_: int) -> bool:
        barrier.wait()
        with Session(db.engine) as s, s.begin():
            try:
                take_number(s, MSISDN)
                return True
            except AlreadyTaken:
                return False

    with ThreadPoolExecutor(max_workers=racers) as pool:
        results = [f.result() for f in [pool.submit(attempt, i) for i in range(racers)]]

    assert results.count(True) == 1
    assert results.count(False) == racers - 1
