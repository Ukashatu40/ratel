"""The suspend, reinstate and terminate flows. Only this module drives these state changes.

Every move goes through domain.state_machine.validate_transition(). No other code path
sets a line's state directly. Storage is through LinesRepository and (when the caller
provides one) the Idempotency store, not a session.
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
from app.bss_lines.models.lines import Line
from app.bss_lines.repositories.idempotency import (
    IdempotencyConflictError,
    IdempotencyStore,
    StoredResult,
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


# The actor written to the audit trail for changes the system makes by itself.
RATING_JOB = "system:rating-job"


class LifecycleError(Exception):
    """A legitimate refusal: wrong state, RatelLink said no, or corrupt stored data."""


@dataclass(frozen=True)
class LifecycleResult:
    line_id: int
    from_state: LineState
    to_state: LineState


def _replay(
    idempotency: IdempotencyStore | None,
    endpoint: str,
    idempotency_key: str,
    line_id: int,
) -> LifecycleResult | None:
    if idempotency is None:
        return None
    saved = idempotency.get(endpoint, idempotency_key)
    if saved is None:
        return None
    if saved.line_id != line_id:
        raise IdempotencyConflictError("this Idempotency-Key was used for another line")
    return LifecycleResult(
        line_id=saved.line_id,
        from_state=LineState(saved.from_state),
        to_state=LineState(saved.to_state),
    )


def _save(
    idempotency: IdempotencyStore | None,
    endpoint: str,
    idempotency_key: str,
    result: LifecycleResult,
) -> None:
    if idempotency is None:
        return
    idempotency.put(
        endpoint,
        idempotency_key,
        StoredResult(
            line_id=result.line_id,
            from_state=result.from_state.value,
            to_state=result.to_state.value,
        ),
    )


def _run(
    lines: LinesRepository,
    client: RatelLinkClientProto,
    idempotency: IdempotencyStore | None,
    line_id: int,
    *,
    endpoint: str,
    target: LineState,
    actor: str,
    reason: str,
    reason_text: str | None,
    idempotency_key: str,
    on_exhaustion: OnExhaustion | None = None,
    state_before_suspension: LineState | None = None,
) -> LifecycleResult:
    """Replay if the key was seen for this line; otherwise do the move.

    On the first call: load, validate, call RatelLink, save, audit, commit.
    """
    replayed = _replay(idempotency, endpoint, idempotency_key, line_id)
    if replayed is not None:
        return replayed

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

    result = LifecycleResult(line.line_id, transition.from_state, transition.to_state)
    _save(idempotency, endpoint, idempotency_key, result)
    return result


def _on_exhaustion_of(line: Line) -> OnExhaustion:
    """What the line's plan does when the allowance runs out."""
    try:
        return OnExhaustion(line.plan.on_exhaustion)
    except ValueError:
        raise LifecycleError(
            f"plan {line.plan_id} has unknown on_exhaustion {line.plan.on_exhaustion!r}"
        ) from None


def suspend_line(
    lines: LinesRepository,
    client: RatelLinkClientProto,
    idempotency: IdempotencyStore,
    line_id: int,
    *,
    actor: str,
    reason: str,
    reason_text: str | None = None,
    idempotency_key: str,
) -> LifecycleResult:
    """active or out_of_data -> suspended. Calls RatelLink /deactivate.

    A repeat with the same Idempotency-Key for the same line returns the first
    result. A repeat for a different line raises IdempotencyConflictError.
    """
    return _run(
        lines,
        client,
        idempotency,
        line_id,
        endpoint="/suspend",
        target=LineState.SUSPENDED,
        actor=actor,
        reason=reason,
        reason_text=reason_text,
        idempotency_key=idempotency_key,
    )


def reinstate_line(
    lines: LinesRepository,
    client: RatelLinkClientProto,
    idempotency: IdempotencyStore,
    line_id: int,
    *,
    actor: str,
    reason: str,
    reason_text: str | None = None,
    idempotency_key: str,
) -> LifecycleResult:
    """suspended -> the state it had before. Calls /activate, then /data if it was out_of_data."""
    replayed = _replay(idempotency, "/reinstate", idempotency_key, line_id)
    if replayed is not None:
        return replayed

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

    on_exhaustion = _on_exhaustion_of(line) if previous is LineState.OUT_OF_DATA else None

    return _run(
        lines,
        client,
        idempotency,
        line_id,
        endpoint="/reinstate",
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
    idempotency: IdempotencyStore,
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
        idempotency,
        line_id,
        endpoint="/terminate",
        target=LineState.TERMINATED,
        actor=actor,
        reason=reason,
        reason_text=reason_text,
        idempotency_key=idempotency_key,
    )

    line = lines.get(line_id)
    if line is not None and line.state == LineState.TERMINATED.value:
        lines.retire_sim(line.iccid)
        lines.commit()

    return result


def mark_out_of_data(
    lines: LinesRepository,
    client: RatelLinkClientProto,
    line_id: int,
    *,
    idempotency_key: str,
    idempotency: IdempotencyStore | None = None,
) -> LifecycleResult:
    """active -> out_of_data, the allowance is used up. Calls /data with the plan's mode.

    The `idempotency` store is optional: the rating job does not pass one (a
    fresh key per run means replay never applies), and any other caller may.
    """
    line = lines.get(line_id)
    if line is None:
        raise LifecycleError(f"line {line_id} not found")
    return _run(
        lines,
        client,
        idempotency,
        line_id,
        endpoint="/data",
        target=LineState.OUT_OF_DATA,
        actor=RATING_JOB,
        reason="allowance_used_up",
        reason_text=None,
        idempotency_key=idempotency_key,
        on_exhaustion=_on_exhaustion_of(line),
    )


def expire_line(
    lines: LinesRepository,
    client: RatelLinkClientProto,
    line_id: int,
    *,
    idempotency_key: str,
    idempotency: IdempotencyStore | None = None,
) -> LifecycleResult:
    """active or out_of_data -> expired, the validity ended without a renewal. Calls /deactivate."""
    return _run(
        lines,
        client,
        idempotency,
        line_id,
        endpoint="/expire",
        target=LineState.EXPIRED,
        actor=RATING_JOB,
        reason="validity_ended",
        reason_text=None,
        idempotency_key=idempotency_key,
    )


def restore_line(
    lines: LinesRepository,
    client: RatelLinkClientProto,
    line_id: int,
    *,
    idempotency_key: str,
    idempotency: IdempotencyStore | None = None,
) -> LifecycleResult:
    """expired -> active, a plan or bundle bought from the wallet. Calls /activate.

    `bss_money`'s rating job asks for this when the wallet covers a renewal, so
    a top-up brings data back by itself. The state machine and the RatelLink call
    stay here, in `bss_lines` (docs/DEPENDENCIES.md).

    The `idempotency` store is optional, same reason as mark_out_of_data.
    """
    return _run(
        lines,
        client,
        idempotency,
        line_id,
        endpoint="/restore",
        target=LineState.ACTIVE,
        actor=RATING_JOB,
        reason="allowance_restored",
        reason_text=None,
        idempotency_key=idempotency_key,
    )
