"""The SIM key store: Ki and OPc are encrypted before they reach the repository.

This is the only place plaintext keys are handled. Nothing here logs. `get_keys` is for the
activation path (W2-02) and `has_same_keys` is for recognising a repeated import (W2-01): the
decrypted values live only for the length of the call. No endpoint returns what they give back.
"""

from __future__ import annotations

import hmac
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


def _normal(value: SecretStr) -> bytes:
    return value.get_secret_value().lower().encode()


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

        This never overwrites and does not compare: `has_same_keys` answers whether a repeat is the
        same import or a conflicting one.
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

    def has_same_keys(self, imsi: str, ki: SecretStr, opc: SecretStr) -> bool:
        """True if the stored Ki and OPc for this IMSI equal these (hex case does not matter).

        Both values are always compared, in constant time, so the answer does not reveal which one
        differs. False if the IMSI has no keys.
        """
        check_key_hex(ki)
        check_key_hex(opc)
        stored = self.get_keys(imsi)
        if stored is None:
            return False
        ki_same = hmac.compare_digest(_normal(stored.ki), _normal(ki))
        opc_same = hmac.compare_digest(_normal(stored.opc), _normal(opc))
        return ki_same and opc_same

    def _encrypt(self, imsi: str, field: FieldName, value: SecretStr) -> Envelope:
        check_key_hex(value)
        return encrypt_field(self._key_provider, imsi, field, value.get_secret_value().encode())

    def _decrypt(self, imsi: str, field: FieldName, envelope: Envelope) -> SecretStr:
        return SecretStr(decrypt_field(self._key_provider, imsi, field, envelope).decode())
