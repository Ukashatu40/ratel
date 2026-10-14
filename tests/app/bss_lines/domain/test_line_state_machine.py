"""Every row of the state table, every pair of states, and every failure path.

The point of this module is refusal: a move not in the Build Plan's table must
raise InvalidTransition every time. Failure paths are tested as carefully as the
allowed ones.

Source: Build Plan, RatelBSS: lines, "Line states" table; issue #29 (W2-13).
"""

from __future__ import annotations

import ast
import itertools
from pathlib import Path

import pytest

from app.bss_lines.domain import (
    DataMode,
    InvalidSuspensionState,
    InvalidTransition,
    LineState,
    OnExhaustion,
    RatelLinkCall,
    Transition,
    validate_transition,
)

ALL_STATES: list[LineState] = list(LineState)


def activate() -> RatelLinkCall:
    return RatelLinkCall("/activate")


def deactivate() -> RatelLinkCall:
    return RatelLinkCall("/deactivate")


def data(mode: DataMode) -> RatelLinkCall:
    return RatelLinkCall("/data", mode)


# ---------------------------------------------------------------------------
# The 15 allowed pairs, one test each.
# ---------------------------------------------------------------------------


def test_awaiting_activation_to_active_calls_activate() -> None:
    t = validate_transition(LineState.AWAITING_ACTIVATION, LineState.ACTIVE)
    assert t.calls == (activate(),)


@pytest.mark.parametrize(
    ("on_exhaustion", "expected_mode"),
    [
        (OnExhaustion.SLOW, DataMode.SLOW),
        (OnExhaustion.STOP, DataMode.OFF),
    ],
)
def test_active_to_out_of_data_uses_on_exhaustion(
    on_exhaustion: OnExhaustion, expected_mode: DataMode
) -> None:
    t = validate_transition(LineState.ACTIVE, LineState.OUT_OF_DATA, on_exhaustion=on_exhaustion)
    assert t.calls == (data(expected_mode),)


def test_out_of_data_to_active_uses_full_mode() -> None:
    t = validate_transition(LineState.OUT_OF_DATA, LineState.ACTIVE)
    assert t.calls == (data(DataMode.FULL),)


def test_active_to_expired_calls_deactivate() -> None:
    t = validate_transition(LineState.ACTIVE, LineState.EXPIRED)
    assert t.calls == (deactivate(),)


def test_out_of_data_to_expired_calls_deactivate() -> None:
    t = validate_transition(LineState.OUT_OF_DATA, LineState.EXPIRED)
    assert t.calls == (deactivate(),)


def test_expired_to_active_calls_activate() -> None:
    t = validate_transition(LineState.EXPIRED, LineState.ACTIVE)
    assert t.calls == (activate(),)


def test_active_to_suspended_calls_deactivate() -> None:
    t = validate_transition(LineState.ACTIVE, LineState.SUSPENDED)
    assert t.calls == (deactivate(),)


def test_out_of_data_to_suspended_calls_deactivate() -> None:
    t = validate_transition(LineState.OUT_OF_DATA, LineState.SUSPENDED)
    assert t.calls == (deactivate(),)


def test_suspended_to_active_restores_with_activate() -> None:
    t = validate_transition(
        LineState.SUSPENDED,
        LineState.ACTIVE,
        state_before_suspension=LineState.ACTIVE,
    )
    assert t.calls == (activate(),)


@pytest.mark.parametrize(
    ("on_exhaustion", "expected_mode"),
    [
        (OnExhaustion.SLOW, DataMode.SLOW),
        (OnExhaustion.STOP, DataMode.OFF),
    ],
)
def test_suspended_to_out_of_data_restores_with_activate_then_data(
    on_exhaustion: OnExhaustion, expected_mode: DataMode
) -> None:
    t = validate_transition(
        LineState.SUSPENDED,
        LineState.OUT_OF_DATA,
        state_before_suspension=LineState.OUT_OF_DATA,
        on_exhaustion=on_exhaustion,
    )
    assert t.calls == (activate(), data(expected_mode))


@pytest.mark.parametrize(
    "from_state",
    [
        LineState.AWAITING_ACTIVATION,
        LineState.ACTIVE,
        LineState.OUT_OF_DATA,
        LineState.EXPIRED,
        LineState.SUSPENDED,
    ],
)
def test_every_state_except_terminated_can_terminate(from_state: LineState) -> None:
    t = validate_transition(from_state, LineState.TERMINATED)
    assert t.calls == (deactivate(),)


# ---------------------------------------------------------------------------
# All 36 pairs: exactly the allowed ones pass, every other pair raises.
# ---------------------------------------------------------------------------


# The 15 allowed pairs. Kept here as data so the 36-pair test can check against it.
ALLOWED_PAIRS: frozenset[tuple[LineState, LineState]] = frozenset(
    {
        (LineState.AWAITING_ACTIVATION, LineState.ACTIVE),
        (LineState.ACTIVE, LineState.OUT_OF_DATA),
        (LineState.OUT_OF_DATA, LineState.ACTIVE),
        (LineState.ACTIVE, LineState.EXPIRED),
        (LineState.OUT_OF_DATA, LineState.EXPIRED),
        (LineState.EXPIRED, LineState.ACTIVE),
        (LineState.ACTIVE, LineState.SUSPENDED),
        (LineState.OUT_OF_DATA, LineState.SUSPENDED),
        (LineState.SUSPENDED, LineState.ACTIVE),
        (LineState.SUSPENDED, LineState.OUT_OF_DATA),
        (LineState.AWAITING_ACTIVATION, LineState.TERMINATED),
        (LineState.ACTIVE, LineState.TERMINATED),
        (LineState.OUT_OF_DATA, LineState.TERMINATED),
        (LineState.EXPIRED, LineState.TERMINATED),
        (LineState.SUSPENDED, LineState.TERMINATED),
    }
)

# States a line can be suspended from. Terminating a suspended line is allowed
# regardless of the previous state, so TERMINATED is not in this set.
RESTORABLE_FROM: frozenset[LineState] = frozenset({LineState.ACTIVE, LineState.OUT_OF_DATA})


def _call_kwargs(from_state: LineState, to_state: LineState) -> dict[str, object]:
    """The extra keyword arguments a pair needs, if any."""
    kwargs: dict[str, object] = {}
    if from_state is LineState.SUSPENDED and to_state is not LineState.TERMINATED:
        # The only legal "previous" that matches the target is the target itself.
        kwargs["state_before_suspension"] = to_state
    if (from_state is LineState.ACTIVE and to_state is LineState.OUT_OF_DATA) or (
        from_state is LineState.SUSPENDED and to_state is LineState.OUT_OF_DATA
    ):
        kwargs["on_exhaustion"] = OnExhaustion.SLOW
    return kwargs


@pytest.mark.parametrize(
    ("from_state", "to_state"),
    sorted(itertools.product(ALL_STATES, repeat=2), key=lambda p: (p[0].value, p[1].value)),
)
def test_every_pair_is_either_allowed_or_refused(
    from_state: LineState, to_state: LineState
) -> None:
    allowed = (from_state, to_state) in ALLOWED_PAIRS
    kwargs = _call_kwargs(from_state, to_state)

    if allowed:
        transition = validate_transition(from_state, to_state, **kwargs)
        assert isinstance(transition, Transition)
        assert transition.from_state is from_state
        assert transition.to_state is to_state
        assert len(transition.calls) >= 1
        return

    # A `suspended -> X` (X != terminated) is refused two ways:
    #   - if X is not the stored previous state: InvalidTransition (the move itself is wrong)
    #   - if X == previous but previous is not a restorable state: InvalidSuspensionState
    #     (the stored data is wrong, and the code must say so loudly)
    if from_state is LineState.SUSPENDED and to_state is not LineState.TERMINATED:
        previous = kwargs.get("state_before_suspension")
        if previous is not None and previous in RESTORABLE_FROM:
            with pytest.raises(InvalidTransition):
                validate_transition(from_state, to_state, **kwargs)
        else:
            with pytest.raises(InvalidSuspensionState):
                validate_transition(from_state, to_state, **kwargs)
        return

    with pytest.raises(InvalidTransition):
        validate_transition(from_state, to_state, **kwargs)


# ---------------------------------------------------------------------------
# Failure paths.
# ---------------------------------------------------------------------------


def test_terminated_cannot_go_to_active() -> None:
    with pytest.raises(InvalidTransition):
        validate_transition(LineState.TERMINATED, LineState.ACTIVE)


def test_terminated_cannot_terminate_itself() -> None:
    with pytest.raises(InvalidTransition):
        validate_transition(LineState.TERMINATED, LineState.TERMINATED)


def test_terminated_cannot_be_restored() -> None:
    for target in ALL_STATES:
        with pytest.raises(InvalidTransition):
            validate_transition(LineState.TERMINATED, target)


def test_awaiting_activation_cannot_skip_to_out_of_data() -> None:
    with pytest.raises(InvalidTransition):
        validate_transition(LineState.AWAITING_ACTIVATION, LineState.OUT_OF_DATA)


def test_active_cannot_go_directly_to_active() -> None:
    with pytest.raises(InvalidTransition):
        validate_transition(LineState.ACTIVE, LineState.ACTIVE)


def test_suspended_requires_state_before_suspension() -> None:
    with pytest.raises(InvalidTransition):
        validate_transition(LineState.SUSPENDED, LineState.ACTIVE)


def test_suspended_cannot_return_to_a_different_state() -> None:
    with pytest.raises(InvalidTransition):
        validate_transition(
            LineState.SUSPENDED,
            LineState.ACTIVE,
            state_before_suspension=LineState.OUT_OF_DATA,
        )


def test_suspended_can_terminate_regardless_of_previous_state() -> None:
    """Terminating a suspended line is allowed from any previous state.

    state_before_suspension is irrelevant for -> terminated: we are not restoring.
    """
    for previous in ALL_STATES:
        t = validate_transition(
            LineState.SUSPENDED,
            LineState.TERMINATED,
            state_before_suspension=previous,
        )
        assert t.calls == (deactivate(),)


def test_suspended_from_a_non_restorable_state_is_refused_loudly() -> None:
    """A stored previous state that is not active or out_of_data is wrong.

    The table has no `awaiting_activation -> suspended`, `expired -> suspended`
    or `suspended -> suspended` row, so a line cannot legitimately be suspended
    from those. If we see one stored, the data is wrong: refuse loudly.
    """
    for previous in (LineState.AWAITING_ACTIVATION, LineState.EXPIRED, LineState.SUSPENDED):
        with pytest.raises(InvalidSuspensionState):
            validate_transition(
                LineState.SUSPENDED,
                previous,
                state_before_suspension=previous,
            )


def test_active_to_out_of_data_requires_on_exhaustion() -> None:
    with pytest.raises(InvalidTransition):
        validate_transition(LineState.ACTIVE, LineState.OUT_OF_DATA)


def test_suspended_to_out_of_data_requires_on_exhaustion() -> None:
    with pytest.raises(InvalidTransition):
        validate_transition(
            LineState.SUSPENDED,
            LineState.OUT_OF_DATA,
            state_before_suspension=LineState.OUT_OF_DATA,
        )


def test_unknown_states_are_rejected() -> None:
    with pytest.raises(TypeError):
        validate_transition("active", LineState.TERMINATED)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Shape rules: calls is always a tuple, and the shapes are consistent.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("from_state", "to_state"),
    sorted(ALLOWED_PAIRS, key=lambda p: (p[0].value, p[1].value)),
)
def test_every_allowed_pair_returns_a_tuple_of_calls(
    from_state: LineState, to_state: LineState
) -> None:
    kwargs = _call_kwargs(from_state, to_state)
    transition = validate_transition(from_state, to_state, **kwargs)
    assert isinstance(transition.calls, tuple)
    assert len(transition.calls) in (1, 2)
    for call in transition.calls:
        assert isinstance(call, RatelLinkCall)
        assert call.endpoint in ("/activate", "/data", "/deactivate")


def test_data_call_always_carries_a_mode() -> None:
    for pair in ALLOWED_PAIRS:
        kwargs = _call_kwargs(*pair)
        transition = validate_transition(*pair, **kwargs)
        for call in transition.calls:
            if call.endpoint == "/data":
                assert call.mode in (DataMode.FULL, DataMode.SLOW, DataMode.OFF)
            else:
                assert call.mode is None


def test_ratel_link_call_refuses_data_without_a_mode() -> None:
    with pytest.raises(ValueError):
        RatelLinkCall("/data")


def test_ratel_link_call_refuses_a_mode_on_activate() -> None:
    with pytest.raises(ValueError):
        RatelLinkCall("/activate", DataMode.FULL)


def test_transition_refuses_no_calls() -> None:
    with pytest.raises(ValueError):
        Transition(LineState.ACTIVE, LineState.ACTIVE, ())


# ---------------------------------------------------------------------------
# Purity: the domain module imports nothing it must not.
# ---------------------------------------------------------------------------


def test_domain_module_imports_only_stdlib_and_pydantic() -> None:
    """The domain layer may not import FastAPI, SQLAlchemy, ratel_link or drivers.

    tests/architecture/test_layers.py enforces this for the whole layer; this
    local check keeps the rule visible in the file that would break it.
    """
    source = Path("services/app/bss_lines/domain.py").read_text()
    forbidden_roots = {
        "fastapi",
        "starlette",
        "sqlalchemy",
        "alembic",
        "pymongo",
        "motor",
        "redis",
        "cryptography",
        "ratel_link",
        "meter_agent",
        "app",  # bss_lines must not import its siblings either
    }
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in forbidden_roots, (
                    f"domain.py must not import {alias.name}"
                )
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            assert node.module.split(".")[0] not in forbidden_roots, (
                f"domain.py must not import from {node.module}"
            )
