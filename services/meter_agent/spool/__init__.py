"""Disk spool with ordered replay (W2-15).

No network access. The sender is passed in.
"""

from .readings import MAX_AGE_SECONDS, ReadingStore
from .spool import Sender, Spool, SpoolResult

__all__ = ["MAX_AGE_SECONDS", "ReadingStore", "Sender", "Spool", "SpoolResult"]
