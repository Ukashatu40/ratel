"""SQLAlchemy implementation of LinesRepository.

This is the only file in bss_lines that imports models.lines or uses a
SQLAlchemy session.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.bss_lines.models.lines import Line, LineAudit, Sim


class SqlLinesRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, line_id: int) -> Line | None:
        return self._session.get(Line, line_id)

    def find_by_identifier(
        self,
        *,
        line_id: int | None = None,
        msisdn: str | None = None,
        iccid: str | None = None,
        imsi: str | None = None,
    ) -> Line | None:
        """Look a line up by exactly one identifier. None if none matches.

        Exactly one of line_id, msisdn, iccid, imsi must be given; the others
        must be None. Raises ValueError if zero or more than one is supplied.
        """
        identifiers = [line_id is not None, msisdn is not None, iccid is not None, imsi is not None]
        if sum(identifiers) != 1:
            raise ValueError("exactly one of line_id, msisdn, iccid, imsi must be given")
        if line_id is not None:
            return self._session.get(Line, line_id)
        stmt = select(Line)
        if msisdn is not None:
            stmt = stmt.where(Line.msisdn == msisdn)
        elif iccid is not None:
            stmt = stmt.where(Line.iccid == iccid)
        elif imsi is not None:
            stmt = stmt.where(Line.imsi == imsi)
        return self._session.execute(stmt).scalar_one_or_none()

    def save(self, line: Line) -> None:
        self._session.add(line)

    def retire_sim(self, iccid: str) -> None:
        """Mark a SIM retired. Used when a line is terminated."""
        sim = self._session.get(Sim, iccid)
        if sim is not None:
            sim.state = "retired"

    def add_audit(
        self,
        *,
        line_id: int,
        from_state: str,
        to_state: str,
        actor: str,
        reason: str,
    ) -> None:
        self._session.add(
            LineAudit(
                line_id=line_id,
                from_state=from_state,
                to_state=to_state,
                actor=actor,
                reason=reason,
            )
        )

    def commit(self) -> None:
        self._session.commit()
