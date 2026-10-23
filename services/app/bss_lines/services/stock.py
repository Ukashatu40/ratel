"""Take a free SIM or number for a new line.

The guarantee: a SIM (or number) cannot be taken by two callers at once. The
atomic UPDATE with WHERE state='in_stock' does this in one statement — the
database serialises the update, and exactly one caller sees one row returned.
The rest see zero rows and get `AlreadyTaken`.

Build Plan, RatelBSS: lines: "A SIM or number cannot be taken twice, even by
simultaneous requests."
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session


class AlreadyTaken(Exception):
    """Another caller already took this SIM or number. Nothing was changed.

    Carries no value: the caller already has the ICCID or MSISDN, and an
    exception message that repeated it would leak it into a traceback or a log
    line, which the project's rules forbid.
    """


@dataclass(frozen=True)
class TakenSim:
    iccid: str
    imsi: str
    batch: str


@dataclass(frozen=True)
class TakenNumber:
    msisdn: str


def take_sim(session: Session, iccid: str) -> TakenSim:
    """Take a free SIM by ICCID. Returns its IMSI and batch.

    Raises AlreadyTaken (with no value) if the SIM is not in_stock.
    """
    row = session.execute(
        text(
            "UPDATE sim SET state = 'in_use', updated_at = now() "
            "WHERE iccid = :iccid AND state = 'in_stock' "
            "RETURNING iccid, imsi, batch"
        ),
        {"iccid": iccid},
    ).first()
    if row is None:
        raise AlreadyTaken
    return TakenSim(iccid=row.iccid, imsi=row.imsi, batch=row.batch)


def take_number(session: Session, msisdn: str) -> TakenNumber:
    """Take a free number. Raises AlreadyTaken (with no value) if not available."""
    row = session.execute(
        text(
            "UPDATE number SET state = 'in_use', updated_at = now() "
            "WHERE msisdn = :msisdn AND state = 'available' "
            "RETURNING msisdn"
        ),
        {"msisdn": msisdn},
    ).first()
    if row is None:
        raise AlreadyTaken
    return TakenNumber(msisdn=row.msisdn)
