"""SQLAlchemy implementation of LinesRepository.

This is the only file in bss_lines that imports models.lines or uses a
SQLAlchemy session.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.bss_lines.models.lines import Line, LineAudit, Sim


class SqlLinesRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, line_id: int) -> Line | None:
        return self._session.get(Line, line_id)

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
