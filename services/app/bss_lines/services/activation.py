"""The activation flow. Only this module drives state changes.

Everything in this module goes through domain.state_machine.validate_transition().
No other code path may set a line's state directly.

It talks to storage through LinesRepository (repositories/ports.py) and the
Idempotency store (repositories/idempotency.py), not through a database session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.bss_lines.domain.state_machine import (
    InvalidTransition,
    LineState,
    validate_transition,
)
from app.bss_lines.repositories.idempotency import IdempotencyStore, StoredResult
from app.bss_lines.repositories.ports import LinesRepository


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


@dataclass(frozen=True)
class ActivationResult:
    line_id: int
    from_state: LineState
    to_state: LineState


def activate_line(
    lines: LinesRepository,
    client: RatelLinkClientProto,
    idempotency: IdempotencyStore,
    line_id: int,
    *,
    actor: str,
    idempotency_key: str,
) -> ActivationResult:
    """Run the sell-to-activate flow for one line.

    A repeat with the same Idempotency-Key returns the first result and changes
    nothing (M-26). Otherwise:
      1. Load the line.
      2. Refuse if KYC is not verified.
      3. Ask the state machine (must be awaiting_activation -> active).
      4. Execute the RatelLink call.
      5. Set state, write audit, commit.
      6. Save the result under the key.
    """
    saved = idempotency.get("/activate", idempotency_key)
    if saved is not None:
        return ActivationResult(
            line_id=saved.line_id,
            from_state=LineState(saved.from_state),
            to_state=LineState(saved.to_state),
        )

    line = lines.get(line_id)
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
