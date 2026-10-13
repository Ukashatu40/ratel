"""What an audit entry says about a line's state: names and numbers, never keys."""

from __future__ import annotations

from typing import Any

from ratel_link.domain.line_state import LineState


def audit_view(state: LineState | None) -> dict[str, Any] | None:
    """The state fields an audit entry records. None for a line that had no state yet."""
    if state is None:
        return None
    return {
        "status": state.status,
        "msisdn": state.msisdn,
        "apns": list(state.apns),
        "ue_ip": state.ue_ip,
        "speed_ul_mbps": state.speed_ul_mbps,
        "speed_dl_mbps": state.speed_dl_mbps,
        "data_mode": state.data_mode,
    }
