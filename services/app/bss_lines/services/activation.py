"""The activation flow. Only this module drives state changes.

Everything in this module goes through domain.state_machine.validate_transition().
No other code path may set a line's state directly.

It talks to storage through LinesRepository (repositories/ports.py) and the
Idempotency store (repositories/idempotency.py), not through a database session.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.bss_lines.domain.state_machine import (
    InvalidTransition,
    LineState,
    validate_transition,
)
from app.bss_lines.repositories.idempotency import (
    IdempotencyConflictError,
    IdempotencyStore,
    StoredResult,
)
from app.bss_lines.repositories.ports import LinesRepository, PaidPlanCheck


class RatelLinkClientProto(Protocol):
    """Anything that can call RatelLink's /activate."""

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


class LineNotFoundError(ActivationError):
    """There is no line with this id."""


@dataclass(frozen=True)
class ActivationResult:
    line_id: int
    from_state: LineState
    to_state: LineState


def _check_replay(
    idempotency: IdempotencyStore,
    endpoint: str,
    idempotency_key: str,
    line_id: int,
) -> ActivationResult | None:
    saved = idempotency.get(endpoint, idempotency_key)
    if saved is None:
        return None
    if saved.line_id != line_id:
        raise IdempotencyConflictError("this Idempotency-Key was used for another line")
    return ActivationResult(
        line_id=saved.line_id,
        from_state=LineState(saved.from_state),
        to_state=LineState(saved.to_state),
    )


def activate_line(
    lines: LinesRepository,
    client: RatelLinkClientProto,
    idempotency: IdempotencyStore,
    line_id: int,
    *,
    actor: str,
    idempotency_key: str,
    paid_plan: PaidPlanCheck,
    now: datetime,
) -> ActivationResult:
    """Run the sell-to-activate flow for one line.

    Refused unless KYC is verified and a plan has been paid for: the line must hold an allowance
    with data left (PRODUCT_RULES.md, line lifecycle). How the first plan is paid for at the
    counter is still open, but every way ends in a purchase, which creates the allowance.

    A repeat with the same Idempotency-Key for the same line returns the first
    result and changes nothing (M-26). A repeat for a *different* line raises
    IdempotencyConflictError: a key names one operation, not a template.

    Two simultaneous requests with the same key can both run; the second fails
    at the state machine (active -> active is refused). SET ... NX would reserve
    the key first; until then the state machine is what stops the double effect.
    """
    replayed = _check_replay(idempotency, "/activate", idempotency_key, line_id)
    if replayed is not None:
        return replayed

    line = lines.get(line_id)
    if line is None:
        raise LineNotFoundError(f"line {line_id} not found")

    if line.customer.kyc_status != "verified":
        raise ActivationError("KYC is not verified; activation is refused")

    try:
        transition = validate_transition(LineState(line.state), LineState.ACTIVE)
    except InvalidTransition as exc:
        raise ActivationError(str(exc)) from exc

    if not paid_plan.has_paid_allowance(line.line_id, now):
        raise ActivationError("No plan has been paid for; activation is refused")

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
            raise ActivationError(f"unexpected RatelLink call: {call.endpoint}")

    line.state = transition.to_state.value
    lines.save(line)
    lines.add_audit(
        line_id=line.line_id,
        from_state=transition.from_state.value,
        to_state=transition.to_state.value,
        actor=actor,
        reason="customer activation",
    )
    lines.commit()

    result = ActivationResult(line.line_id, transition.from_state, transition.to_state)
    idempotency.put(
        "/activate",
        idempotency_key,
        StoredResult(
            line_id=result.line_id,
            from_state=result.from_state.value,
            to_state=result.to_state.value,
        ),
    )
    return result
