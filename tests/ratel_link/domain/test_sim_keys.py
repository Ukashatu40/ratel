"""SIM key domain: the key format rule and the decrypted holder."""

import dataclasses
import json

import pytest
from pydantic import SecretStr
from pydantic_core import to_json

from ratel_link.domain.sim_keys import SimKeys, check_key_hex
from tests.synthetic import (
    SENTINEL_OPC,
    SYNTHETIC_IMSI,
    SYNTHETIC_KI_HEX,
    SYNTHETIC_OPC_HEX,
)

HEX_KI = SYNTHETIC_KI_HEX


HEX_OPC = SYNTHETIC_OPC_HEX.upper()  # upper case hex is valid too


def test_check_key_hex_message_has_no_value() -> None:
    with pytest.raises(ValueError, match="32 hexadecimal") as exc:
        check_key_hex(SecretStr(SENTINEL_OPC))
    assert SENTINEL_OPC not in str(exc.value)


def test_sim_keys_hide_secrets_and_cannot_be_serialised() -> None:
    keys = SimKeys(imsi=SYNTHETIC_IMSI, ki=SecretStr(HEX_KI), opc=SecretStr(HEX_OPC))
    for text in (repr(keys), str(keys), f"{keys}", f"{keys!r}", to_json(keys).decode()):
        assert HEX_KI not in text
        assert HEX_OPC not in text
    assert SYNTHETIC_IMSI not in repr(keys)
    with pytest.raises(TypeError):
        json.dumps(dataclasses.asdict(keys))
    with pytest.raises(dataclasses.FrozenInstanceError):
        keys.ki = SecretStr("x")  # type: ignore[misc]
    # Even a plain tuple of the fields keeps the values masked.
    assert HEX_KI not in repr(dataclasses.astuple(keys))
