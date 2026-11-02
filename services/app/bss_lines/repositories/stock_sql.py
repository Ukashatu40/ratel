"""Put SIMs and numbers into stock, and count them. For the stock command, not a request."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.bss_lines.domain.stock import SimEntry
from app.bss_lines.models.lines import Number, Sim


class StockConflict(Exception):
    """A SIM in the file clashes with one in stock (an ICCID with another IMSI, or the reverse).

    Carries no value: the identifiers stay out of messages. Nothing was loaded.
    """


@dataclass(frozen=True)
class Loaded:
    added: int
    skipped: int  # already in stock exactly as in the file


class SqlStockLoader:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_sims(self, entries: list[SimEntry]) -> Loaded:
        iccids = [e.iccid for e in entries]
        imsis = [e.imsi for e in entries]
        by_iccid = {
            s.iccid: s for s in self._session.scalars(select(Sim).where(Sim.iccid.in_(iccids)))
        }
        by_imsi = {s.imsi: s for s in self._session.scalars(select(Sim).where(Sim.imsi.in_(imsis)))}
        added = skipped = 0
        for e in entries:
            same_iccid, same_imsi = by_iccid.get(e.iccid), by_imsi.get(e.imsi)
            if same_iccid is not None and same_iccid.imsi == e.imsi:
                skipped += 1
                continue
            if same_iccid is not None or same_imsi is not None:
                raise StockConflict
            self._session.add(Sim(iccid=e.iccid, imsi=e.imsi, batch=e.batch, state="in_stock"))
            added += 1
        return Loaded(added, skipped)

    def add_numbers(self, msisdns: list[str]) -> Loaded:
        have = set(self._session.scalars(select(Number.msisdn).where(Number.msisdn.in_(msisdns))))
        fresh = [m for m in msisdns if m not in have]
        self._session.add_all(Number(msisdn=m, state="available") for m in fresh)
        return Loaded(len(fresh), len(have))

    def summary(self) -> dict[str, dict[str, int]]:
        def count(model: type[Sim] | type[Number]) -> dict[str, int]:
            rows = self._session.execute(
                select(model.state, func.count()).group_by(model.state)
            ).all()
            return {state: n for state, n in rows}

        return {"sims": count(Sim), "numbers": count(Number)}
