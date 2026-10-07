"""AES-256-GCM envelope encryption for Ki and OPc at rest (docs/adr/0006).

Each field is stored as its own envelope:

    {"v": 1, "alg": "AES-256-GCM", "kid": "<key id>", "nonce": "<base64>", "ct": "<base64>"}

`ct` is the ciphertext with the 16-byte GCM tag appended. The nonce is 12 fresh random bytes per
encryption, never derived and never reused. The associated data binds the ciphertext to its
record, field and key id, so a ciphertext copied to another IMSI or from `ki` to `opc` fails to
decrypt. Nothing here puts plaintext, ciphertext or key bytes in an exception message.
"""

from __future__ import annotations

import base64
import binascii
import secrets
from collections.abc import Mapping
from typing import Any, Literal, TypedDict

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ratel_link.key_provider import KEY_BYTES, KeyProvider, KeyUnavailableError

ALGORITHM = "AES-256-GCM"
ENVELOPE_VERSION = 1
NONCE_BYTES = 12  # 96 bits, the size GCM is designed for
_TAG_BYTES = 16
_AAD_PREFIX = b"ratel-link|sim_key|v1|"

FieldName = Literal["ki", "opc"]


class Envelope(TypedDict):
    v: int
    alg: str
    kid: str
    nonce: str
    ct: str


class DecryptionError(Exception):
    """Decryption failed: wrong key, wrong record, or altered data. Deliberately says no more."""

    def __init__(self) -> None:
        super().__init__("decryption failed")


def _aad(imsi: str, field: FieldName, kid: str) -> bytes:
    # `field` and `kid` cannot contain "|" (a Literal and a validated setting), so reading the
    # last two segments from the right is unambiguous whatever the IMSI contains.
    return _AAD_PREFIX + imsi.encode() + b"|" + field.encode() + b"|" + kid.encode()


def _key_for(provider: KeyProvider, kid: str) -> bytes:
    key = provider.get_key(kid)
    if len(key) != KEY_BYTES:
        # AESGCM would accept 16 or 24 bytes and silently weaken the cipher. Refuse.
        raise KeyUnavailableError(f"the key provider returned a key that is not {KEY_BYTES} bytes")
    return key


def encrypt_field(provider: KeyProvider, imsi: str, field: FieldName, plaintext: bytes) -> Envelope:
    kid = provider.current_key_id()
    key = _key_for(provider, kid)
    nonce = secrets.token_bytes(NONCE_BYTES)
    ct = AESGCM(key).encrypt(nonce, plaintext, _aad(imsi, field, kid))
    return {
        "v": ENVELOPE_VERSION,
        "alg": ALGORITHM,
        "kid": kid,
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ct": base64.b64encode(ct).decode("ascii"),
    }


def decrypt_field(
    provider: KeyProvider, imsi: str, field: FieldName, envelope: Mapping[str, Any]
) -> bytes:
    try:
        if envelope["v"] != ENVELOPE_VERSION or envelope["alg"] != ALGORITHM:
            raise DecryptionError
        kid = envelope["kid"]
        nonce = base64.b64decode(envelope["nonce"], validate=True)
        ct = base64.b64decode(envelope["ct"], validate=True)
        if not isinstance(kid, str) or len(nonce) != NONCE_BYTES or len(ct) < _TAG_BYTES:
            raise DecryptionError
    except (KeyError, TypeError, ValueError, binascii.Error):
        raise DecryptionError from None
    key = _key_for(provider, kid)  # an unknown key id raises KeyUnavailableError: fail closed
    try:
        return AESGCM(key).decrypt(nonce, ct, _aad(imsi, field, kid))
    except InvalidTag:
        raise DecryptionError from None
