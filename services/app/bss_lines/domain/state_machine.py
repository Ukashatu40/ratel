"""The line state machine: which moves between line states are allowed, and what
RatelLink calls each allowed move implies.

Pure rules only. No database, no web framework, no network, no logging, no clock,
no knowledge of plans or RatelLink's speed fields. This is the only place in
RatelBSS that says what a legal transition is; nothing else may update a line's
state directly.

Source: Build Plan, RatelBSS: lines, "Line states" table and rules.

15 allowed pairs out of the 36 possible:
  1.  awaiting_activation -> active              /activate
  2.  active              -> out_of_data         /data (slow or off, per on_exhaustion)
  3.  out_of_data         -> active              /data (full)
  4.  active              -> expired             /deactivate
  5.  out_of_data         -> expired             /deactivate
  6.  expired             -> active              /activate
  7.  active              -> suspended           /deactivate
  8.  out_of_data         -> suspended           /deactivate
  9.  suspended           -> active              /activate
  10. suspended           -> out_of_data         /activate, then /data
  11. awaiting_activation -> terminated          /deactivate
  12. active              -> terminated          /deactivate
  13. out_of_data         -> terminated          /deactivate
  14. expired             -> terminated          /deactivate
  15. suspended           -> terminated          /deactivate

Everything else is refused. In particular:
  - terminated -> terminated is refused (already terminated).
  - terminated -> any other state is refused (a terminated line cannot be revived).
  - awaiting_activation -> out_of_data (and any other skip) is refused.
  - suspended -> X is allowed only if X equals the stored previous state, and
    that previous state must be active or out_of_data.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LineState(StrEnum):
    """The six states a line can be in (Build Plan, "Line states")."""

    AWAITING_ACTIVATION = "awaiting_activation"
    ACTIVE = "active"
    OUT_OF_DATA = "out_of_data"
    EXPIRED = "expired"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class DataMode(StrEnum):
    """The `mode` argument of a /data call.

    `full` restores the plan's full speeds, `slow` uses the plan's slow speeds,
    `off` removes the internet APN. The plan's actual speed numbers are the
    caller's business, not this module's.
    """

    FULL = "full"
    SLOW = "slow"
    OFF = "off"


class OnExhaustion(StrEnum):
    """A plan's policy for what happens when the data allowance is used up.

    `slow` keeps the line online at the plan's slow speeds; `stop` cuts internet
    entirely. Calls still work in both cases. This enum exists so the caller
    cannot pass a free string that would silently fall through.
    """

    SLOW = "slow"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class RatelLinkCall:
    """One call to RatelLink. `mode` is set only for /data."""

    endpoint: str
    mode: DataMode | None = None

    def __post_init__(self) -> None:
        if self.endpoint == "/data" and self.mode is None:
            raise ValueError("/data requires a mode")
        if self.endpoint != "/data" and self.mode is not None:
            raise ValueError(f"{self.endpoint} does not take a mode")


@dataclass(frozen=True, slots=True)
class Transition:
    """An allowed move: from where, to where, and the RatelLink calls it implies.

    `calls` is always a tuple, even when there is only one call, so the caller
    can always loop over it. Restoring a suspended out_of_data line is
    `(/activate, /data)` in that order: activating puts the line at full speed,
    the /data call then slows or cuts it again.
    """

    from_state: LineState
    to_state: LineState
    calls: tuple[RatelLinkCall, ...]

    def __post_init__(self) -> None:
        if not self.calls:
            raise ValueError("a transition must imply at least one call")


class InvalidTransition(Exception):
    """Raised when a move is not in the table. Carries both states for the caller."""

    def __init__(self, from_state: LineState, to_state: LineState) -> None:
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(f"{from_state.value} -> {to_state.value} is not an allowed transition")


class InvalidSuspensionState(Exception):
    """The stored `state_before_suspension` is not a state a line can be suspended from.

    The table has no `terminated -> suspended` row, so a line cannot legitimately
    be suspended from `terminated`. If this error fires, the stored data is wrong
    and the caller should not silently continue.
    """

    def __init__(self, previous: LineState | None) -> None:
        self.previous = previous
        shown = "<missing>" if previous is None else previous.value
        super().__init__(
            f"a line cannot have been suspended from state {shown!r}; "
            "the stored state_before_suspension is wrong"
        )


_ACTIVATE = RatelLinkCall("/activate")
_DEACTIVATE = RatelLinkCall("/deactivate")


_STATIC_TRANSITIONS: dict[tuple[LineState, LineState], tuple[RatelLinkCall, ...]] = {
    (LineState.AWAITING_ACTIVATION, LineState.ACTIVE): (_ACTIVATE,),
    (LineState.OUT_OF_DATA, LineState.ACTIVE): (RatelLinkCall("/data", DataMode.FULL),),
    (LineState.ACTIVE, LineState.EXPIRED): (_DEACTIVATE,),
    (LineState.OUT_OF_DATA, LineState.EXPIRED): (_DEACTIVATE,),
    (LineState.EXPIRED, LineState.ACTIVE): (_ACTIVATE,),
    (LineState.ACTIVE, LineState.SUSPENDED): (_DEACTIVATE,),
    (LineState.OUT_OF_DATA, LineState.SUSPENDED): (_DEACTIVATE,),
}


_SUSPENDABLE_FROM = frozenset({LineState.ACTIVE, LineState.OUT_OF_DATA})


def _data_mode(on_exhaustion: OnExhaustion | None) -> DataMode:
    """Map a plan's on_exhaustion policy to the /data mode it implies."""
    if on_exhaustion is OnExhaustion.SLOW:
        return DataMode.SLOW
    if on_exhaustion is OnExhaustion.STOP:
        return DataMode.OFF
    # Callers must not reach here: they check first. Raise loudly if they do.
    raise ValueError(
        f"on_exhaustion must be OnExhaustion.SLOW or OnExhaustion.STOP, got {on_exhaustion!r}"
    )


def _restore_from_suspension(
    previous: LineState | None, on_exhaustion: OnExhaustion | None
) -> tuple[RatelLinkCall, ...]:
    """The calls to bring a suspended line back to its previous state.

    - previous `active`      -> (/activate,)
    - previous `out_of_data` -> (/activate, /data with the mode from on_exhaustion)

    `previous` must be active or out_of_data. Anything else (including `terminated`
    and None) raises InvalidSuspensionState: the stored data is wrong.
    """
    if previous not in _SUSPENDABLE_FROM:
        raise InvalidSuspensionState(previous)
    if previous is LineState.ACTIVE:
        return (_ACTIVATE,)
    # previous is out_of_data
    if on_exhaustion is None:
        raise _MissingOnExhaustion
    return (_ACTIVATE, RatelLinkCall("/data", _data_mode(on_exhaustion)))


class _MissingOnExhaustion(Exception):
    """Internal sentinel. Never leaves this module; validate_transition catches it."""


def _terminate(from_state: LineState) -> tuple[RatelLinkCall, ...]:
    """Terminating is allowed from every state except `terminated` itself."""
    if from_state is LineState.TERMINATED:
        raise InvalidTransition(from_state, LineState.TERMINATED)
    return (_DEACTIVATE,)


def validate_transition(
    from_state: LineState,
    to_state: LineState,
    *,
    state_before_suspension: LineState | None = None,
    on_exhaustion: OnExhaustion | None = None,
) -> Transition:
    """Is this move allowed, and what RatelLink calls does it imply?

    Returns a Transition whose `calls` is always an ordered tuple (one or two items).

    Raises:
      InvalidTransition          the move is not in the table.
      InvalidSuspensionState     a suspended line's stored previous state is wrong.

    `state_before_suspension` is required when `from_state` is SUSPENDED, and is
    ignored for every other move. `on_exhaustion` is required for
    `active -> out_of_data` and for restoring a suspended `out_of_data` line, and
    is ignored for every other move.
    """
    if not isinstance(from_state, LineState) or not isinstance(to_state, LineState):
        raise TypeError("from_state and to_state must be LineState values")

    # 1. Restoring a suspended line: back to the state it had before.
    if from_state is LineState.SUSPENDED and to_state is not LineState.TERMINATED:
        if to_state is not state_before_suspension:
            raise InvalidTransition(from_state, to_state)
        try:
            calls = _restore_from_suspension(state_before_suspension, on_exhaustion)
        except _MissingOnExhaustion:
            raise InvalidTransition(from_state, to_state) from None
        return Transition(from_state, to_state, calls)

    # 2. Any other state -> terminated.
    if to_state is LineState.TERMINATED:
        calls = _terminate(from_state)
        return Transition(from_state, to_state, calls)

    # 3. active -> out_of_data: the mode depends on the plan's on_exhaustion.
    if from_state is LineState.ACTIVE and to_state is LineState.OUT_OF_DATA:
        if on_exhaustion is None:
            raise InvalidTransition(from_state, to_state)
        return Transition(
            from_state, to_state, (RatelLinkCall("/data", _data_mode(on_exhaustion)),)
        )

    # 4. Everything else: a static row, or refused.
    row = _STATIC_TRANSITIONS.get((from_state, to_state))
    if row is None:
        raise InvalidTransition(from_state, to_state)
    return Transition(from_state, to_state, row)
