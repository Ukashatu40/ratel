"""One row of the S-CSCF's accounting, as the export command prints it."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CallRow:
    table: str  # "acc" (an answered INVITE, or a BYE) or "missed" (an INVITE that failed)
    row_id: int
    method: str
    sip_code: int
    call_id: str
    from_tag: str
    from_user: str
    to_user: str
    time: int  # epoch seconds, UTC: when the final reply passed the S-CSCF
    start_ts: (
        int  # epoch seconds, UTC: when the request arrived; 0 on rows from before it was recorded
    )

    def __repr__(self) -> str:  # a number or a Call-ID must never reach a log through a repr
        return f"CallRow(table={self.table!r}, row_id={self.row_id})"
