"""What should happen to a line, judged from its allowance alone.

Pure: no database, no clock (the moment to judge at is passed in), no logging. The rating job
(services/rating_job.py) calls this after it has deducted usage, and acts on the answer.

- Every bucket has expired and none is still to come: the validity ended without a renewal, so the
  line expires (Build Plan, RatelBSS: money).
- Between plans (the old bucket ended and a renewal starts later) nothing is done: no bucket is
  valid now, but the validity has not ended for good either.
- A bucket is valid now but nothing is left in the valid buckets: the line is out of data. What
  that means for the line, slow or cut, is the plan's `on_exhaustion`, applied by the state machine.
- An out-of-data or expired line that has allowance again is restored: a purchase only creates the
  bucket, and this brings the line back. Doing it here and not in the purchase means a RatelLink
  outage at that moment is retried by the next run, with no extra bookkeeping.
- A line that never had a bucket is left alone. A line created by hand in the lab, or one whose
  first purchase has not been recorded yet, has no allowance to judge it by, and cutting it would
  be a guess. TODO(PRD): whether a line with no allowance counts as out of data (see rating.py).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum

from app.bss_lines.domain.state_machine import LineState
from app.bss_money.domain.allowance import Bucket


class ServiceAction(StrEnum):
    NONE = "none"
    OUT_OF_DATA = "out_of_data"
    EXPIRE = "expire"
    RESTORE = "restore"


def action_for(state: LineState, buckets: Iterable[Bucket], now: datetime) -> ServiceAction:
    """The one change this line needs now, if any. Calling it again after the change gives NONE."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware (UTC)")
    if state not in (LineState.ACTIVE, LineState.OUT_OF_DATA, LineState.EXPIRED):
        return ServiceAction.NONE
    held = list(buckets)
    if not held:
        return ServiceAction.NONE
    current = [b for b in held if b.is_valid_at(now)]
    remaining = sum(b.remaining_bytes for b in current)
    if state is LineState.EXPIRED:
        # A purchase made after the line expired (a top-up that covered a plan) brings it back.
        return ServiceAction.RESTORE if remaining > 0 else ServiceAction.NONE
    if all(b.valid_to <= now for b in held):
        return ServiceAction.EXPIRE
    if not current:  # between plans: the old one ended and a renewal starts later
        return ServiceAction.NONE
    if state is LineState.OUT_OF_DATA:
        # Allowance came back (a bundle or a plan was bought): data returns at full speed.
        return ServiceAction.RESTORE if remaining > 0 else ServiceAction.NONE
    return ServiceAction.OUT_OF_DATA if remaining == 0 else ServiceAction.NONE
