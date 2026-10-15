"""Pure domain types and rules for the RatelMeter data agent (W2-14).

No file, network or database access.
"""

from .intervals import INTERVAL_SECONDS, build_record, increase, interval_bounds
from .records import Increase, Reading, UsageRecord

__all__ = [
    "INTERVAL_SECONDS",
    "Increase",
    "Reading",
    "UsageRecord",
    "build_record",
    "increase",
    "interval_bounds",
]
