"""Exception types for counter reading and parsing.

Reading counters has exactly two outcomes: readings, or an error. Nothing that goes wrong is ever
turned into an empty result, because an empty result means "no usage" and usage would be lost
silently.
"""

from __future__ import annotations


class CounterReadError(Exception):
    """The counters could not be read. The agent skips the interval and logs the error type."""


class MalformedSnapshotError(CounterReadError, ValueError):
    """A counter snapshot cannot be parsed or breaks an invariant."""


class CounterUnavailableError(CounterReadError):
    """The source of the counters could not be reached (nft missing, failed, or timed out)."""
