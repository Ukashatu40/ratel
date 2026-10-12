"""Report a line's status (GET /v1/lines/{imsi}), so RatelBSS can check its view against ours.

Reads only what RatelLink last wrote. A SIM whose keys are stored but which has no service yet is
`provisioned`. Nothing here reads a key: it asks the key store only whether one exists.
"""

from __future__ import annotations

from ratel_link.domain.identifiers import is_imsi
from ratel_link.domain.line_state import LineView
from ratel_link.repositories.ports import LineStateRepository, SimKeyRepository


class LineStatusService:
    def __init__(self, lines: LineStateRepository, sims: SimKeyRepository) -> None:
        self._lines = lines
        self._sims = sims

    def get(self, imsi: str) -> LineView | None:
        """The line's status, or None if RatelLink has never heard of this IMSI."""
        if not is_imsi(imsi):
            raise ValueError("invalid IMSI")
        state = self._lines.get(imsi)
        if state is not None:
            return LineView.from_state(state)
        if self._sims.exists(imsi):
            return LineView.provisioned()
        return None
