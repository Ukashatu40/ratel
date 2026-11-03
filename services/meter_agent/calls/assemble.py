"""Joining the rows of each call into one record. Pure: no file, no network, no database.

The rules are the agreement's (docs/call-record-agreement.md, section 11), each proven on the lab on
2026-10-30 and 2026-11-02:

- A call answered: an `acc` INVITE 200. It is *open* until its first BYE (the lowest id) appears;
  then it is finished with `completed`. An answered call that never gets a BYE is not posted:
  after `open_max_seconds` it is dropped and counted (the contract has no open-ended call).
- A call not answered: only `missed_calls` rows, written together. Several rows of one call can
  carry different codes (a callee in airplane mode gave 408 and 500): the reason comes from the set.
- `started_at` is the smallest `start_ts` of the call's INVITE rows (0 means "not recorded": then
  the time of the row is the best there is).
- Both legs of a call share one Call-ID and write one row each, so a call is its Call-ID.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .rows import CallRow

_DIGITS = re.compile(r"[^0-9]")


def normalise_msisdn(raw: str) -> str:
    """`0XXXXXXXXXX` and `+234XXXXXXXXXX` become `234XXXXXXXXXX`. A number that matches no rule is
    kept as it came (never drop a call), without spaces or SIP parameters. Empty becomes "unknown".
    """
    number = raw.split(";", 1)[0].strip().replace(" ", "")
    if not number:
        return "unknown"
    digits = _DIGITS.sub("", number)
    if number.startswith("+") and re.fullmatch(r"234[0-9]{10}", digits):
        return digits
    if re.fullmatch(r"234[0-9]{10}", digits) and number == digits:
        return digits
    if re.fullmatch(r"0[0-9]{10}", number):
        return "234" + number[1:]
    return number[:32]


def reason_for(codes: set[int]) -> str:
    """The `end_reason` of a call that was never answered, from the SIP codes of its failed rows."""
    if 487 in codes:
        return "cancelled"
    if 603 in codes:
        return "declined"
    if codes & {486, 600}:
        return "not_answered"
    if codes & {408, 500, 404, 480}:
        return "unavailable"
    return "failed"


@dataclass(frozen=True, slots=True)
class OpenCall:
    """An answered call that has not ended yet. Kept between polls."""

    call_id: str
    from_msisdn: str
    to_msisdn: str
    started_at: int
    answered_at: int


@dataclass(slots=True)
class Assembled:
    finished: list[dict[str, object]] = field(default_factory=list)
    open_calls: dict[str, OpenCall] = field(default_factory=dict)
    acc_id: int = 0
    missed_id: int = 0
    orphan_byes: int = 0  # a BYE for a call this agent never saw answered
    stale_dropped: int = 0  # answered, and no BYE after `open_max_seconds`


def _started(rows: list[CallRow]) -> int:
    known = [r.start_ts for r in rows if r.start_ts > 0]
    return min(known) if known else min(r.time for r in rows)


def _record(
    call_id: str, frm: str, to: str, started: int, answered: int | None, ended: int, reason: str
) -> dict[str, object]:
    return {
        "call_id": call_id,
        "from_msisdn": frm,
        "to_msisdn": to,
        "started_at": started,
        "answered_at": answered,
        "ended_at": ended,
        "end_reason": reason,
    }


def assemble(
    rows: list[CallRow],
    open_calls: dict[str, OpenCall],
    *,
    now: int,
    open_max_seconds: int,
    acc_id: int = 0,
    missed_id: int = 0,
) -> Assembled:
    answered: dict[str, list[CallRow]] = {}
    byes: dict[str, list[CallRow]] = {}
    failed: dict[str, list[CallRow]] = {}
    for row in sorted(rows, key=lambda r: (r.table, r.row_id)):
        if row.table == "acc":
            acc_id = max(acc_id, row.row_id)
            if row.method == "INVITE" and row.sip_code == 200:
                answered.setdefault(row.call_id, []).append(row)
            elif row.method == "BYE":
                byes.setdefault(row.call_id, []).append(row)
        else:
            missed_id = max(missed_id, row.row_id)
            if row.method == "INVITE":
                failed.setdefault(row.call_id, []).append(row)

    result = Assembled(acc_id=acc_id, missed_id=missed_id)
    still_open = dict(open_calls)

    for call_id, invites in answered.items():
        first = invites[0]
        known = still_open.get(call_id)
        started = _started(invites)
        answered_at = min(r.time for r in invites)
        if known is not None:
            started, answered_at = (
                min(known.started_at, started),
                min(known.answered_at, answered_at),
            )
        still_open[call_id] = OpenCall(
            call_id,
            known.from_msisdn if known else normalise_msisdn(first.from_user),
            known.to_msisdn if known else normalise_msisdn(first.to_user),
            started,
            answered_at,
        )

    for call_id, group in byes.items():
        call = still_open.pop(call_id, None)
        if call is None:
            result.orphan_byes += 1
            continue
        ended = group[0].time  # the lowest id: the first hang-up
        result.finished.append(
            _record(
                call.call_id,
                call.from_msisdn,
                call.to_msisdn,
                call.started_at,
                call.answered_at,
                ended,
                "completed",
            )
        )

    for call_id, group in failed.items():
        if call_id in still_open or call_id in answered or call_id in byes:
            continue  # it was answered: a failed branch of the same call does not undo that
        first = group[0]
        result.finished.append(
            _record(
                call_id,
                normalise_msisdn(first.from_user),
                normalise_msisdn(first.to_user),
                _started(group),
                None,
                max(r.time for r in group),
                reason_for({r.sip_code for r in group}),
            )
        )

    for call_id, call in list(still_open.items()):
        if now - call.answered_at > open_max_seconds:
            del still_open[call_id]
            result.stale_dropped += 1
    result.open_calls = still_open
    return result
