import dataclasses
import json

import pytest
from pydantic import SecretStr, ValidationError
from pydantic_core import to_json

from ratel_link.models import SimImport, SimKeys, check_key_hex, is_imsi
from tests.synthetic import (
    SENTINEL_KI,
    SENTINEL_OPC,
    SYNTHETIC_IMSI,
    SYNTHETIC_KI_HEX,
    SYNTHETIC_OPC_HEX,
)

HEX_KI = SYNTHETIC_KI_HEX
HEX_OPC = SYNTHETIC_OPC_HEX.upper()  # upper case hex is valid too


def test_valid_import_parses() -> None:
    m = SimImport(imsi=SYNTHETIC_IMSI, ki=SecretStr(HEX_KI), opc=SecretStr(HEX_OPC))
    assert m.ki.get_secret_value() == HEX_KI
    assert m.opc.get_secret_value() == HEX_OPC  # upper case hex is accepted too


def test_import_model_masks_secrets_in_every_text_form() -> None:
    m = SimImport.model_validate({"imsi": SYNTHETIC_IMSI, "ki": HEX_KI, "opc": HEX_OPC})
    for text in (repr(m), str(m), m.model_dump_json(), to_json(m).decode(), str(m.model_dump())):
        assert HEX_KI not in text
        assert HEX_OPC not in text


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "0011",
        HEX_KI + "0",  # 33 characters
        HEX_KI[:-1],  # 31 characters
        "g" + HEX_KI[1:],  # not hex
        HEX_KI + "\n",  # trailing newline must not slip past an anchored pattern
        " " + HEX_KI,
        SENTINEL_KI,
    ],
)
@pytest.mark.parametrize("field", ["ki", "opc"])
def test_bad_key_format_is_rejected_without_echoing_it(field: str, bad: str) -> None:
    body = {"imsi": SYNTHETIC_IMSI, "ki": HEX_KI, "opc": HEX_OPC, field: bad}
    with pytest.raises(ValidationError) as exc:
        SimImport.model_validate(body)
    # str() and repr() are what end up in logs and tracebacks. (.errors() keeps the raw input by
    # pydantic's design: never log it. The HTTP handler reads only the field names, see below.)
    text = str(exc.value) + repr(exc.value)
    assert bad.strip() == "" or bad not in text
    assert field in text


@pytest.mark.parametrize(
    "imsi", ["", "62100000000000", "6210000000000012", "62100000000000a", " " * 15]
)
def test_bad_imsi_is_rejected(imsi: str) -> None:
    with pytest.raises(ValidationError):
        SimImport(imsi=imsi, ki=SecretStr(HEX_KI), opc=SecretStr(HEX_OPC))


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        SimImport.model_validate(
            {"imsi": SYNTHETIC_IMSI, "ki": HEX_KI, "opc": HEX_OPC, "amf": "8000"}
        )


def test_is_imsi() -> None:
    assert is_imsi(SYNTHETIC_IMSI)
    assert not is_imsi(SYNTHETIC_IMSI + "\n")
    assert not is_imsi({"$ne": ""})
    assert not is_imsi(None)


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


def test_invalid_import_over_http_does_not_echo_the_keys() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from common.errors import install_error_handlers

    app = FastAPI()
    install_error_handlers(app)

    @app.post("/sims")
    async def sims(body: SimImport) -> dict[str, str]:
        return {"ok": "yes"}

    r = TestClient(app).post(
        "/sims", json={"imsi": SYNTHETIC_IMSI, "ki": SENTINEL_KI, "opc": SENTINEL_OPC}
    )
    assert r.status_code == 422
    assert SENTINEL_KI not in r.text and SENTINEL_OPC not in r.text
    assert r.json() == {
        "error": {
            "code": "validation_error",
            "message": "Invalid request. Fields: body.ki, body.opc",
        }
    }
