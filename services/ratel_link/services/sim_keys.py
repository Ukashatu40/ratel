"""The SIM key store: Ki and OPc are encrypted before they reach the repository.

This is the only place plaintext keys are handled. Nothing here logs, and `get_keys` is meant for
the activation path only (W2-02). No endpoint returns what it gives back.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from pydantic import SecretStr

from common.timeutil import utc_now
from ratel_link.domain.identifiers import is_imsi
from ratel_link.domain.sim_keys import Envelope, SimKeyDocument, SimKeys, check_key_hex
from ratel_link.repositories.ports import SimKeyRepository
from ratel_link.security.crypto import FieldName, decrypt_field, encrypt_field
from ratel_link.security.key_provider import KeyProvider


def _require_imsi(imsi: str) -> None:
    # The store is the persistence boundary: only a validated IMSI ever reaches a query.
    if not is_imsi(imsi):
        raise ValueError("invalid IMSI")


class SimKeyStore:
    def __init__(
        self,
        repository: SimKeyRepository,
        key_provider: KeyProvider,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._key_provider = key_provider
        self._now = now

    def put_if_absent(self, imsi: str, ki: SecretStr, opc: SecretStr) -> bool:
        """Encrypt and store a SIM's keys. False if the IMSI already has keys (nothing changes).

        What the API should do when an existing IMSI arrives with DIFFERENT keys is not decided
        (DECISIONS_PENDING.md). This method never overwrites and does not compare.
        """
        _require_imsi(imsi)
        document: SimKeyDocument = {
            "imsi": imsi,
            "ki": self._encrypt(imsi, "ki", ki),
            "opc": self._encrypt(imsi, "opc", opc),
            "created_at": self._now(),
        }
        return self._repository.insert_if_absent(document)

    def get_keys(self, imsi: str) -> SimKeys | None:
        _require_imsi(imsi)
        document = self._repository.get(imsi)
        if document is None:
            return None
        return SimKeys(
            imsi=imsi,
            ki=self._decrypt(imsi, "ki", document["ki"]),
            opc=self._decrypt(imsi, "opc", document["opc"]),
        )

    def _encrypt(self, imsi: str, field: FieldName, value: SecretStr) -> Envelope:
        check_key_hex(value)
        return encrypt_field(self._key_provider, imsi, field, value.get_secret_value().encode())

    def _decrypt(self, imsi: str, field: FieldName, envelope: Envelope) -> SecretStr:
        return SecretStr(decrypt_field(self._key_provider, imsi, field, envelope).decode())
