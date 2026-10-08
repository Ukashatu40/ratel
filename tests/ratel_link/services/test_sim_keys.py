import base64
import json

import pytest
from pydantic import SecretStr

from ratel_link.security.crypto import DecryptionError
from ratel_link.security.key_provider import KeyUnavailableError, NoKeyProvider
from ratel_link.services.sim_keys import SimKeyStore
from tests.ratel_link.fakes import FakeClock, InMemorySimKeyRepository, StaticKeyProvider
from tests.synthetic import (
    SENTINEL_KI,
    SENTINEL_OPC,
    SYNTHETIC_IMSI,
    SYNTHETIC_IMSI_2,
    SYNTHETIC_KI_HEX,
    SYNTHETIC_OPC_HEX,
)

HEX_KI = SYNTHETIC_KI_HEX
HEX_OPC = SYNTHETIC_OPC_HEX


def _store(
    repo: InMemorySimKeyRepository | None = None, provider: StaticKeyProvider | None = None
) -> tuple[SimKeyStore, InMemorySimKeyRepository, FakeClock]:
    repo = repo or InMemorySimKeyRepository()
    clock = FakeClock()
    return SimKeyStore(repo, provider or StaticKeyProvider(), clock), repo, clock


def test_stored_document_holds_no_plaintext() -> None:
    store, repo, _ = _store()
    assert store.put_if_absent(SYNTHETIC_IMSI, SecretStr(HEX_KI), SecretStr(HEX_OPC)) is True
    raw = repo.documents[SYNTHETIC_IMSI]
    text = json.dumps(raw, default=str)
    assert HEX_KI not in text and HEX_OPC not in text
    assert HEX_KI.encode() not in base64.b64decode(raw["ki"]["ct"])
    assert set(raw) == {"imsi", "ki", "opc", "created_at"}  # no `amf`, no plaintext field
    assert set(raw["ki"]) == {"v", "alg", "kid", "nonce", "ct"}


def test_created_at_is_utc_from_the_injected_clock() -> None:
    store, repo, clock = _store()
    store.put_if_absent(SYNTHETIC_IMSI, SecretStr(HEX_KI), SecretStr(HEX_OPC))
    assert repo.documents[SYNTHETIC_IMSI]["created_at"] == clock()
    assert repo.documents[SYNTHETIC_IMSI]["created_at"].utcoffset().total_seconds() == 0  # type: ignore[union-attr]


def test_get_keys_round_trips() -> None:
    store, _, _ = _store()
    store.put_if_absent(SYNTHETIC_IMSI, SecretStr(HEX_KI), SecretStr(HEX_OPC))
    keys = store.get_keys(SYNTHETIC_IMSI)
    assert keys is not None
    assert keys.ki.get_secret_value() == HEX_KI
    assert keys.opc.get_secret_value() == HEX_OPC


def test_unknown_imsi_returns_none() -> None:
    assert _store()[0].get_keys(SYNTHETIC_IMSI) is None


def test_reimport_of_the_same_imsi_creates_no_second_document() -> None:
    store, repo, _ = _store()
    assert store.put_if_absent(SYNTHETIC_IMSI, SecretStr(HEX_KI), SecretStr(HEX_OPC)) is True
    first = json.dumps(repo.documents[SYNTHETIC_IMSI], default=str)
    assert store.put_if_absent(SYNTHETIC_IMSI, SecretStr(HEX_KI), SecretStr(HEX_OPC)) is False
    assert len(repo.documents) == 1
    assert json.dumps(repo.documents[SYNTHETIC_IMSI], default=str) == first


def test_reimport_with_different_keys_does_not_overwrite() -> None:
    store, _, _ = _store()
    store.put_if_absent(SYNTHETIC_IMSI, SecretStr(HEX_KI), SecretStr(HEX_OPC))
    assert store.put_if_absent(SYNTHETIC_IMSI, SecretStr(HEX_OPC), SecretStr(HEX_KI)) is False
    keys = store.get_keys(SYNTHETIC_IMSI)
    assert keys is not None and keys.ki.get_secret_value() == HEX_KI


def test_a_swapped_record_fails_to_decrypt() -> None:
    store, repo, _ = _store()
    store.put_if_absent(SYNTHETIC_IMSI, SecretStr(HEX_KI), SecretStr(HEX_OPC))
    store.put_if_absent(SYNTHETIC_IMSI_2, SecretStr(HEX_OPC), SecretStr(HEX_KI))
    # An attacker with database write access copies one SIM's ciphertext onto another.
    repo.documents[SYNTHETIC_IMSI_2]["ki"] = repo.documents[SYNTHETIC_IMSI]["ki"]
    with pytest.raises(DecryptionError):
        store.get_keys(SYNTHETIC_IMSI_2)


def test_swapped_ki_and_opc_fail_to_decrypt() -> None:
    store, repo, _ = _store()
    store.put_if_absent(SYNTHETIC_IMSI, SecretStr(HEX_KI), SecretStr(HEX_OPC))
    doc = repo.documents[SYNTHETIC_IMSI]
    doc["ki"], doc["opc"] = doc["opc"], doc["ki"]
    with pytest.raises(DecryptionError):
        store.get_keys(SYNTHETIC_IMSI)


def test_no_key_means_nothing_is_stored() -> None:
    repo = InMemorySimKeyRepository()
    with pytest.raises(KeyUnavailableError):
        SimKeyStore(repo, NoKeyProvider()).put_if_absent(
            SYNTHETIC_IMSI, SecretStr(HEX_KI), SecretStr(HEX_OPC)
        )
    assert repo.documents == {}  # never falls back to storing unencrypted


def test_no_key_means_nothing_is_read() -> None:
    store, repo, _ = _store()
    store.put_if_absent(SYNTHETIC_IMSI, SecretStr(HEX_KI), SecretStr(HEX_OPC))
    with pytest.raises(KeyUnavailableError):
        SimKeyStore(repo, NoKeyProvider()).get_keys(SYNTHETIC_IMSI)


@pytest.mark.parametrize("bad", ["", "xyz", HEX_KI[:-1], SENTINEL_KI])
def test_invalid_key_is_refused_before_storage(bad: str) -> None:
    store, repo, _ = _store()
    with pytest.raises(ValueError) as exc:
        store.put_if_absent(SYNTHETIC_IMSI, SecretStr(bad), SecretStr(HEX_OPC))
    assert repo.documents == {}
    assert SENTINEL_KI not in str(exc.value)


@pytest.mark.parametrize("bad", ["", "123", SYNTHETIC_IMSI + "0", "6210000000000a1"])
def test_invalid_imsi_is_refused(bad: str) -> None:
    store, repo, _ = _store()
    with pytest.raises(ValueError, match="invalid IMSI"):
        store.put_if_absent(bad, SecretStr(HEX_KI), SecretStr(HEX_OPC))
    with pytest.raises(ValueError, match="invalid IMSI"):
        store.get_keys(bad)
    assert repo.documents == {}


def test_a_query_operator_cannot_reach_the_repository() -> None:
    store, _, _ = _store()
    with pytest.raises(ValueError):
        store.get_keys({"$ne": ""})  # type: ignore[arg-type]


def test_sentinel_values_never_land_in_a_document() -> None:
    # Sentinels are not valid hex, so use hex of the sentinel text to prove nothing is stored raw.
    store, repo, _ = _store()
    ki = SENTINEL_KI.encode().hex()[:32]
    opc = SENTINEL_OPC.encode().hex()[:32]
    store.put_if_absent(SYNTHETIC_IMSI, SecretStr(ki), SecretStr(opc))
    text = json.dumps(repo.documents, default=str)
    assert ki not in text and opc not in text
