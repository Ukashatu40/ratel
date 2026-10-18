"""The activation flow. Only this module drives state changes.

Everything in this module goes through domain.validate_transition().
No other code path may set a line's state directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from app.bss_lines.domain import (
    InvalidTransition,
    LineState,
    validate_transition,
)
from app.bss_lines.models import Line, LineAudit
from common.logging import log_event

log = logging.getLogger("ratel.bss.lines.activation")


class RatelLinkClientProto(Protocol):
    """Anything that can call RatelLink's /activate.

    The real RatelLinkClient and the test's FakeRatelLinkClient both match this.
    The service does not depend on either concretely.
    """

    def activate(
        self,
        imsi: str,
        *,
        msisdn: str,
        speed_ul_mbps: float,
        speed_dl_mbps: float,
        voice: bool,
        idempotency_key: str,
    ) -> None: ...


class ActivationError(Exception):
    """A legitimate refusal: KYC not verified, wrong state, RatelLink said no."""


@dataclass(frozen=True)
class ActivationResult:
    line_id: int
    from_state: LineState
    to_state: LineState


def activate_line(
    session: Session,
    client: RatelLinkClientProto,
    line_id: int,
    *,
    actor: str,
    idempotency_key: str,
) -> ActivationResult:
    """Run the sell-to-activate flow for one line.

    Order:
      1. Load the line.
      2. Refuse if the customer's KYC is not verified.
      3. Ask the state machine what to do (must be awaiting_activation -> active).
      4. Execute each RatelLink call the transition implies.
      5. Set the line's new state, write an audit entry, commit.
    """
    line = session.get(Line, line_id)
    if line is None:
        raise ActivationError(f"line {line_id} not found")

    if line.customer.kyc_status != "verified":
        raise ActivationError("KYC is not verified; activation is refused")

    try:
        transition = validate_transition(LineState(line.state), LineState.ACTIVE)
    except InvalidTransition as exc:
        raise ActivationError(str(exc)) from exc

    for call in transition.calls:
        if call.endpoint == "/activate":
            client.activate(
                imsi=line.imsi,
                msisdn=line.msisdn,
                speed_ul_mbps=line.plan.speed_ul_mbps,
                speed_dl_mbps=line.plan.speed_dl_mbps,
                voice=True,
                idempotency_key=idempotency_key,
            )
        else:
            # The domain should not imply other calls for awaiting_activation -> active.
            raise ActivationError(f"unexpected RatelLink call: {call.endpoint}")

    line.state = transition.to_state.value
    session.add(
        LineAudit(
            line_id=line.line_id,
            from_state=transition.from_state.value,
            to_state=transition.to_state.value,
            actor=actor,
            reason="customer activation",
        )
    )
    session.commit()

    log_event(
        log,
        logging.INFO,
        "line.activate.succeeded",
        line_id=line.line_id,
        api_key_id=None,  # filled in later by the API layer
    )
    return ActivationResult(line.line_id, transition.from_state, transition.to_state)
