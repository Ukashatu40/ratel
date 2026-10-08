import base64
import copy
import os
from typing import Any

import pytest

from ratel_link.domain.sim_keys import Envelope
from ratel_link.security.crypto import (
    ALGORITHM,
    NONCE_BYTES,
    DecryptionError,
    decrypt_field,
    encrypt_field,
)
from ratel_link.security.key_provider import KEY_BYTES, KeyUnavailableError
from tests.ratel_link.fakes import StaticKeyProvider
from tests.synthetic import SENTINEL_KI, SENTINEL_OPC, SYNTHETIC_IMSI, SYNTHETIC_IMSI_2

PLAINTEXT = SENTINEL_KI.encode()


def _enc(provider: StaticKeyProvider, imsi: str = SYNTHETIC_IMSI, field: Any = "ki") -> Envelope:
    return encrypt_field(provider, imsi, field, PLAINTEXT)


def _flip(b64: str) -> str:
    raw = bytearray(base64.b64decode(b64))
    raw[0] ^= 0x01
    return base64.b64encode(bytes(raw)).decode()


def test_round_trip() -> None:
    p = StaticKeyProvider()
    assert decrypt_field(p, SYNTHETIC_IMSI, "ki", _enc(p)) == PLAINTEXT


def test_envelope_has_exactly_the_documented_shape() -> None:
    env = _enc(StaticKeyProvider(current="7"))
    assert set(env) == {"v", "alg", "kid", "nonce", "ct"}
    assert (env["v"], env["alg"], env["kid"]) == (1, ALGORITHM, "7")
    assert len(base64.b64decode(env["nonce"])) == NONCE_BYTES
    assert len(base64.b64decode(env["ct"])) == len(PLAINTEXT) + 16  # ciphertext plus GCM tag


def test_envelope_contains_no_plaintext() -> None:
    env = _enc(StaticKeyProvider())
    assert SENTINEL_KI not in str(env)
    assert PLAINTEXT not in base64.b64decode(env["ct"])


def test_same_plaintext_encrypts_differently() -> None:
    p = StaticKeyProvider()
    a, b = _enc(p), _enc(p)
    assert a["nonce"] != b["nonce"]
    assert a["ct"] != b["ct"]


def test_ten_thousand_nonces_are_unique() -> None:
    p = StaticKeyProvider()
    nonces = {_enc(p)["nonce"] for _ in range(10_000)}
    assert len(nonces) == 10_000


def test_tampered_ciphertext_fails() -> None:
    p = StaticKeyProvider()
    env = _enc(p)
    env["ct"] = _flip(env["ct"])
    with pytest.raises(DecryptionError):
        decrypt_field(p, SYNTHETIC_IMSI, "ki", env)


def test_tampered_tag_fails() -> None:
    p = StaticKeyProvider()
    env = _enc(p)
    raw = bytearray(base64.b64decode(env["ct"]))
    raw[-1] ^= 0x01
    env["ct"] = base64.b64encode(bytes(raw)).decode()
    with pytest.raises(DecryptionError):
        decrypt_field(p, SYNTHETIC_IMSI, "ki", env)


def test_tampered_nonce_fails() -> None:
    p = StaticKeyProvider()
    env = _enc(p)
    env["nonce"] = _flip(env["nonce"])
    with pytest.raises(DecryptionError):
        decrypt_field(p, SYNTHETIC_IMSI, "ki", env)


def test_ciphertext_moved_to_another_imsi_fails() -> None:
    p = StaticKeyProvider()
    env = _enc(p, SYNTHETIC_IMSI)
    with pytest.raises(DecryptionError):
        decrypt_field(p, SYNTHETIC_IMSI_2, "ki", env)


def test_ciphertext_moved_from_ki_to_opc_fails() -> None:
    p = StaticKeyProvider()
    env = _enc(p, field="ki")
    with pytest.raises(DecryptionError):
        decrypt_field(p, SYNTHETIC_IMSI, "opc", env)


def test_key_id_is_bound_into_the_ciphertext() -> None:
    # Two ids that map to the same key bytes: relabelling an envelope must still fail.
    key = os.urandom(KEY_BYTES)
    p = StaticKeyProvider({"1": key, "2": key}, current="1")
    env = _enc(p)
    env["kid"] = "2"
    with pytest.raises(DecryptionError):
        decrypt_field(p, SYNTHETIC_IMSI, "ki", env)


def test_wrong_key_fails() -> None:
    env = _enc(StaticKeyProvider())
    with pytest.raises(DecryptionError):
        decrypt_field(StaticKeyProvider(), SYNTHETIC_IMSI, "ki", env)  # a different random key


def test_unknown_key_id_fails_closed() -> None:
    env = _enc(StaticKeyProvider(current="1"))
    other = StaticKeyProvider(current="2")
    with pytest.raises(KeyUnavailableError):
        decrypt_field(other, SYNTHETIC_IMSI, "ki", env)


@pytest.mark.parametrize("size", [0, 16, 24, 31, 33, 64])
def test_key_of_wrong_length_is_rejected(size: int) -> None:
    # 16 and 24 are valid AES key sizes. AESGCM would accept them, so the length check matters.
    p = StaticKeyProvider({"1": os.urandom(size)})
    with pytest.raises(KeyUnavailableError):
        _enc(p)
    good = _enc(StaticKeyProvider({"1": os.urandom(KEY_BYTES)}))
    with pytest.raises(KeyUnavailableError):
        decrypt_field(p, SYNTHETIC_IMSI, "ki", good)


def _broken_envelopes() -> dict[str, Any]:
    good = _enc(StaticKeyProvider())

    def with_(**changes: Any) -> dict[str, Any]:
        env: dict[str, Any] = copy.deepcopy(dict(good))
        env.update(changes)
        return env

    def without(name: str) -> dict[str, Any]:
        env: dict[str, Any] = copy.deepcopy(dict(good))
        del env[name]
        return env

    return {
        "wrong_version": with_(v=2),
        "wrong_algorithm": with_(alg="AES-128-GCM"),
        "missing_nonce": without("nonce"),
        "missing_ct": without("ct"),
        "missing_kid": without("kid"),
        "kid_not_a_string": with_(kid=1),
        "nonce_not_base64": with_(nonce="!!!!"),
        "nonce_wrong_length": with_(nonce=base64.b64encode(b"short").decode()),
        "ct_too_short": with_(ct=base64.b64encode(b"x").decode()),
        "ct_not_a_string": with_(ct=None),
    }


@pytest.mark.parametrize("name", sorted(_broken_envelopes()))
def test_malformed_envelope_is_a_decryption_error(name: str) -> None:
    env = _broken_envelopes()[name]
    with pytest.raises((DecryptionError, KeyUnavailableError)):
        decrypt_field(StaticKeyProvider(), SYNTHETIC_IMSI, "ki", env)


def test_failures_do_not_carry_secret_material() -> None:
    provider = StaticKeyProvider()
    key_text = base64.b64encode(provider.get_key("1")).decode()
    env = _enc(provider)
    secrets_in_play = [SENTINEL_KI, SENTINEL_OPC, env["ct"], env["nonce"], key_text]
    failures: list[BaseException] = []
    cases = [
        (StaticKeyProvider(), SYNTHETIC_IMSI, "ki", env),  # wrong key
        (provider, SYNTHETIC_IMSI_2, "ki", env),  # wrong record
        (provider, SYNTHETIC_IMSI, "opc", env),  # wrong field
        (StaticKeyProvider(current="9"), SYNTHETIC_IMSI, "ki", env),  # unknown key id
        (provider, SYNTHETIC_IMSI, "ki", {**env, "ct": "!!"}),  # malformed
    ]
    for p, imsi, field, e in cases:
        with pytest.raises((DecryptionError, KeyUnavailableError)) as caught:
            decrypt_field(p, imsi, field, e)
        failures.append(caught.value)
    for exc in failures:
        for text in (str(exc), repr(exc), str(exc.__cause__), str(exc.__context__)):
            assert not any(s in text for s in secrets_in_play), type(exc).__name__
