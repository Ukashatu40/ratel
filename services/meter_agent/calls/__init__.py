"""Call mode of the RatelMeter agent, on the voice VM (docs/call-record-agreement.md, M-10).

Reads the S-CSCF's `acc` and `missed_calls` tables through a fixed export command, joins the rows of
each call into one record, and posts finished calls to the RatelMeter API. It holds no SQL driver:
the export command is the only thing that touches the database.

Call records are personal data: nothing in this package logs a number or a Call-ID.
"""

from .agent import CallAgent, CallAgentConfig
from .assemble import Assembled, OpenCall, assemble, normalise_msisdn, reason_for
from .rows import CallRow
from .source import CallSource, CallSourceError, CommandCallSource
from .state import CallState, StateStore

__all__ = [
    "Assembled",
    "CallAgent",
    "CallAgentConfig",
    "CallRow",
    "CallSource",
    "CallSourceError",
    "CallState",
    "CommandCallSource",
    "OpenCall",
    "StateStore",
    "assemble",
    "normalise_msisdn",
    "reason_for",
]
