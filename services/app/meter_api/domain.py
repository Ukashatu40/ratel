"""Domain models and business invariants for data usage metering.

Pure logic: no I/O, no database drivers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

IMSI_PATTERN = re.compile(r"^[0-9]{15}$")


@dataclass(frozen=True, slots=True)
class UsageRecord:
    imsi: str
    period_start: int  # UTC epoch seconds
    period_end: int  # UTC epoch seconds
    bytes_up: int
    bytes_down: int

    def validate(self) -> None:
        if not IMSI_PATTERN.match(self.imsi):
            raise ValueError("Invalid IMSI format: must be 15 digits")
        if self.period_start < 0 or self.period_end < 0:
            raise ValueError("Period timestamps must be non-negative")
        if self.bytes_up < 0 or self.bytes_down < 0:
            raise ValueError("Byte counts must be non-negative integers")


# --- call records (docs/call-record-agreement.md) ---------------------------------------------

# PRD decision 8 is still open: these are the values proposed in the agreement, section 11.
# Changing the set means changing contracts/openapi.yaml and the CHECK on call_record together.
END_REASONS = ("completed", "cancelled", "declined", "not_answered", "unavailable", "failed")

# The SIP Call-ID and the numbers are visible ASCII, no spaces (the contract says the same, so a
# request the schema allows is never refused here). A number that matches no rule is sent as it
# came (the agreement: "never drop the call"), so only blanks and absurd lengths are refused.
CALL_ID_PATTERN = re.compile(r"^[!-~]{1,128}$")
NUMBER_PATTERN = re.compile(r"^[!-~]{1,32}$")


@dataclass(frozen=True, slots=True)
class CallRecord:
    call_id: str
    from_msisdn: str
    to_msisdn: str
    started_at: int  # UTC epoch seconds: when the INVITE arrived
    answered_at: int | None  # UTC epoch seconds; None if the call was never answered
    ended_at: (
        int  # UTC epoch seconds: the first BYE, or the final reply of a call that never connected
    )
    end_reason: str

    def validate(self) -> None:
        if not CALL_ID_PATTERN.match(self.call_id):
            raise ValueError("Invalid call_id: 1 to 128 visible characters, no spaces")
        if not NUMBER_PATTERN.match(self.from_msisdn) or not NUMBER_PATTERN.match(self.to_msisdn):
            raise ValueError("Invalid number: 1 to 32 visible characters, no spaces")
        if self.end_reason not in END_REASONS:
            raise ValueError("Invalid end_reason")
        if self.started_at < 0 or self.ended_at < 0 or (self.answered_at or 0) < 0:
            raise ValueError("Call timestamps must be non-negative")
        # The agreement, section 6: answered and completed are the same fact.
        if (self.end_reason == "completed") != (self.answered_at is not None):
            raise ValueError("A call is completed exactly when it was answered")

    def normalised(self) -> CallRecord:
        """The same call with its times in order: it ends no earlier than it starts, and an answer
        falls inside the call. Times from two logs can disagree by a second; one such record must
        not stop a whole batch (the usage store does the same with `period_end`). The caller counts
        how many were changed, never which.
        """
        ended = max(self.ended_at, self.started_at)
        answered = (
            None if self.answered_at is None else min(max(self.answered_at, self.started_at), ended)
        )
        if ended == self.ended_at and answered == self.answered_at:
            return self
        return CallRecord(
            self.call_id, self.from_msisdn, self.to_msisdn, self.started_at, answered, ended,
            self.end_reason,
        )  # fmt: skip
