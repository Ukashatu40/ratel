"""The suspend, reinstate and terminate flows. Only this module drives these state changes.

Every move goes through domain.state_machine.validate_transition(). No other code path
sets a line's state directly. Storage is through LinesRepository, not a session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.bss_lines.domain.state_machine import (
    DataMode,
    InvalidSuspensionState,
    InvalidTransition,
    LineState,
    OnExhaustion,
    validate_transition,
)
from app.bss_lines.repositories.ports import LinesRepository


class RatelLinkClientProto(Protocol):
    """The subset of the RatelLink client this module uses."""

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

    def deactivate(self, imsi: str, *, reason: str, idempotency_key: str) -> None: ...

    def data(
        self,
        imsi: str,
        *,
        mode: str,
        speed_ul_mbps: float | None,
        speed_dl_mbps: float | None,
        idempotency_key: str,
    ) -> None: ...


class LifecycleError(Exception):
    """A legitimate refusal: wrong state, RatelLink said no, or corrupt stored data."""


@dataclass(frozen=True)
class LifecycleResult:
    line_id: int
    from_state: LineState
    to_state: LineState


def _run(
    lines: LinesRepository,
    client: RatelLinkClientProto,
    line_id: int,
    *,
    target: LineState,
    actor: str,
    reason: str,
    reason_text: str | None,
    idempotency_key: str,
    on_exhaustion: OnExhaustion | None = None,
    state_before_suspension: LineState | None = None,
) -> LifecycleResult:
    """Shared body: load, validate, call RatelLink, save, audit, commit."""
    line = lines.get(line_id)
    if line is None:
        raise LifecycleError(f"line {line_id} not found")

    try:
        transition = validate_transition(
            LineState(line.state),
            target,
            state_before_suspension=state_before_suspension,
            on_exhaustion=on_exhaustion,
        )
    except InvalidSuspensionState as exc:
        raise LifecycleError(str(exc)) from exc
    except InvalidTransition as exc:
        raise LifecycleError(str(exc)) from exc

    reason_for_audit = reason if not reason_text else f"{reason}: {reason_text}"

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
        elif call.endpoint == "/deactivate":
            client.deactivate(
                imsi=line.imsi,
                reason=reason_for_audit,
                idempotency_key=idempotency_key,
            )
        elif call.endpoint == "/data":
            assert call.mode is not None
            if call.mode is DataMode.OFF:
                client.data(
                    imsi=line.imsi,
                    mode="off",
                    speed_ul_mbps=None,
                    speed_dl_mbps=None,
                    idempotency_key=idempotency_key,
                )
            else:
                speeds_ul = (
                    line.plan.slow_ul_mbps
                    if call.mode is DataMode.SLOW
                    else line.plan.speed_ul_mbps
                )
                speeds_dl = (
                    line.plan.slow_dl_mbps
                    if call.mode is DataMode.SLOW
                    else line.plan.speed_dl_mbps
                )
                if speeds_ul is None or speeds_dl is None:
                    raise LifecycleError(
                        f"plan {line.plan_id} has on_exhaustion=slow but no slow speeds"
                    )
                client.data(
                    imsi=line.imsi,
                    mode=call.mode.value,
                    speed_ul_mbps=speeds_ul,
                    speed_dl_mbps=speeds_dl,
                    idempotency_key=idempotency_key,
                )
        else:
            raise LifecycleError(f"unexpected RatelLink call: {call.endpoint}")

    # Bookkeeping differs by transition:
    #   -> suspended: remember the state we came from, so reinstate knows where to go back to
    #   anything else:  clear any stale state_before_suspension
    if target is LineState.SUSPENDED:
        line.state_before_suspension = transition.from_state.value
    elif transition.from_state is LineState.SUSPENDED:
        line.state_before_suspension = None

    line.state = transition.to_state.value
    lines.save(line)
    lines.add_audit(
        line_id=line.line_id,
        from_state=transition.from_state.value,
        to_state=transition.to_state.value,
        actor=actor,
        reason=reason_for_audit,
    )
    lines.commit()

    return LifecycleResult(line.line_id, transition.from_state, transition.to_state)


def suspend_line(
    lines: LinesRepository,
    client: RatelLinkClientProto,
    line_id: int,
    *,
    actor: str,
    reason: str,
    reason_text: str | None = None,
    idempotency_key: str,
) -> LifecycleResult:
    """active or out_of_data -> suspended. Calls RatelLink /deactivate."""
    return _run(
        lines,
        client,
        line_id,
        target=LineState.SUSPENDED,
        actor=actor,
        reason=reason,
        reason_text=reason_text,
        idempotency_key=idempotency_key,
    )


def reinstate_line(
    lines: LinesRepository,
    client: RatelLinkClientProto,
    line_id: int,
    *,
    actor: str,
    reason: str,
    reason_text: str | None = None,
    idempotency_key: str,
) -> LifecycleResult:
    """suspended -> the state it had before. Calls /activate, then /data if it was out_of_data."""
    line = lines.get(line_id)
    if line is None:
        raise LifecycleError(f"line {line_id} not found")

    if line.state != LineState.SUSPENDED.value:
        raise LifecycleError(
            f"{line.state} -> {LineState.SUSPENDED.value} is not the suspended state"
        )

    previous_raw = line.state_before_suspension
    if previous_raw is None:
        raise LifecycleError(
            "line is suspended but state_before_suspension is not set; the stored data is wrong"
        )
    try:
        previous = LineState(previous_raw)
    except ValueError as exc:
        raise LifecycleError(
            f"state_before_suspension {previous_raw!r} is not a known state"
        ) from exc

    on_exhaustion: OnExhaustion | None = None
    if previous is LineState.OUT_OF_DATA:
        if line.plan.on_exhaustion == OnExhaustion.SLOW.value:
            on_exhaustion = OnExhaustion.SLOW
        elif line.plan.on_exhaustion == OnExhaustion.STOP.value:
            on_exhaustion = OnExhaustion.STOP
        else:
            raise LifecycleError(
                f"plan {line.plan_id} has unknown on_exhaustion {line.plan.on_exhaustion!r}"
            )

    return _run(
        lines,
        client,
        line_id,
        target=previous,
        actor=actor,
        reason=reason,
        reason_text=reason_text,
        idempotency_key=idempotency_key,
        on_exhaustion=on_exhaustion,
        state_before_suspension=previous,
    )


def terminate_line(
    lines: LinesRepository,
    client: RatelLinkClientProto,
    line_id: int,
    *,
    actor: str,
    reason: str,
    reason_text: str | None = None,
    idempotency_key: str,
) -> LifecycleResult:
    """Any state except terminated -> terminated. Calls /deactivate.

    The SIM is retired and the line's number left in_use. Quarantine of the number
    after termination is compliance's call (PRODUCT_RULES.md, decision 4); the
    period is undecided, so this function does not touch the number's state.
    """
    result = _run(
        lines,
        client,
        line_id,
        target=LineState.TERMINATED,
        actor=actor,
        reason=reason,
        reason_text=reason_text,
        idempotency_key=idempotency_key,
    )

    # Retire the SIM now that the line is terminated.
    line = lines.get(line_id)
    if line is not None:
        lines.retire_sim(line.iccid)
        lines.commit()

    return result
