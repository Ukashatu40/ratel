"""Exception types for counter reading and parsing."""

from __future__ import annotations


class MalformedSnapshotError(ValueError):
    """Raised when a counter snapshot cannot be parsed or violates invariants."""
