"""Reads the lab's voice (`ims`) session from a file.

The file is a subscriber document exported from the lab (extended JSON, as `mongosh` writes it).
Only its `ims` session is used; everything else in it is ignored and never read, so a leftover key
in the file cannot reach a log or a document. Keep the file outside the repository.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from bson import json_util

from ratel_link.domain.subscriber import VoiceTemplateError, ims_session_from_template


class FileVoiceTemplate:
    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._session: dict[str, Any] | None = None

    def ims_session(self) -> dict[str, Any] | None:
        """A copy of the ims session, or None if no file is configured.

        Raises VoiceTemplateError if the file is unreadable or has no usable ims session. The
        message never contains file content.
        """
        if self._path is None:
            return None
        if self._session is None:
            try:
                document = json_util.loads(self._path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise VoiceTemplateError("the voice template file cannot be read") from None
            if not isinstance(document, dict):
                raise VoiceTemplateError("the voice template file is not a document")
            self._session = ims_session_from_template(document)
        return copy.deepcopy(self._session)
