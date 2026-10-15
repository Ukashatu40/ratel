"""Disk spool with ordered replay (W2-15).

No network access. The sender is passed in.
"""
from .spool import Spool, SpoolResult, Sender

__all__ = ["Sender", "Spool", "SpoolResult"]