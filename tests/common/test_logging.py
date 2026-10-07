import json
import logging

import pytest

from common.logging import JsonFormatter, is_sensitive_key, log_event, mask_last4, redact
from tests.synthetic import SENTINEL_API_KEY, SENTINEL_API_SECRET, SENTINEL_KI, SENTINEL_OPC


def _format(**fields: object) -> dict[str, object]:
    rec = logging.LogRecord("t", logging.INFO, __file__, 1, "x", (), None)
    rec.__dict__.update({"event": "test.event", **fields})
    return json.loads(JsonFormatter().format(rec))


def test_ki_and_opc_values_are_redacted() -> None:
    out = _format(ki=SENTINEL_KI, opc=SENTINEL_OPC, imsi_hash="abc")
    text = json.dumps(out)
    assert SENTINEL_KI not in text
    assert SENTINEL_OPC not in text
    assert out["ki"] == "[REDACTED]"
    assert out["imsi_hash"] == "abc"


def test_nested_redaction() -> None:
    out = redact({"sim": {"Ki": "x", "OPc": "y", "kind": "ok"}, "items": [{"api_key": "z"}]})
    assert out == {
        "sim": {"Ki": "[REDACTED]", "OPc": "[REDACTED]", "kind": "ok"},
        "items": [{"api_key": "[REDACTED]"}],
    }


def test_short_names_match_whole_words_only() -> None:
    assert is_sensitive_key("ki")
    assert is_sensitive_key("sim_ki")
    assert is_sensitive_key("pin")
    assert not is_sensitive_key("kind")
    assert not is_sensitive_key("pinned")
    assert not is_sensitive_key("mining")


def test_authorization_and_urls_are_sensitive() -> None:
    for key in ("Authorization", "api_key", "password", "mongo_uri", "database_url", "id_number"):
        assert is_sensitive_key(key), key


def test_mask_last4() -> None:
    assert mask_last4("12345678901234567890") == "*" * 16 + "7890"
    assert mask_last4("123") == "***"


def test_event_is_dotted_name_and_output_is_one_json_line() -> None:
    logger = logging.getLogger("ratel.test")
    log_event(logger, logging.INFO, "line.activate.succeeded", status="active")
    out = _format(status="active")
    assert out["event"] == "test.event"
    assert out["level"] == "INFO"


def test_exception_logs_type_only() -> None:
    try:
        raise ValueError(f"bad key {SENTINEL_KI}")
    except ValueError:
        import sys

        rec = logging.LogRecord("t", logging.ERROR, __file__, 1, "boom", (), sys.exc_info())
    out = json.loads(JsonFormatter().format(rec))
    assert out["exc_type"] == "ValueError"
    assert SENTINEL_KI not in json.dumps(out)


def test_api_key_id_and_generation_are_logged() -> None:
    out = _format(api_key_id="bss-app", api_key_generation=2)
    assert out["api_key_id"] == "bss-app"
    assert out["api_key_generation"] == 2


@pytest.mark.parametrize(
    "key",
    [
        "api_key",
        "authorization",
        "token",
        "bearer",
        "key_hash",
        "secret_hash",
        "ciphertext",
        "plaintext",
        "ki",
        "opc",
        # The allowlist is exact names only. Near misses stay redacted.
        "api_key_id_value",
        "api_key_secret",
        "API_KEY",
    ],
)
def test_credential_like_keys_are_redacted(key: str) -> None:
    out = _format(**{key: SENTINEL_API_KEY})
    assert out[key] == "[REDACTED]"
    assert SENTINEL_API_KEY not in json.dumps(out)


def test_allowlist_does_not_unredact_values_nested_under_other_names() -> None:
    out = redact({"request": {"authorization": SENTINEL_API_KEY, "api_key_id": "bss-app"}})
    assert out == {"request": {"authorization": "[REDACTED]", "api_key_id": "bss-app"}}


def test_api_key_sentinel_has_the_real_token_shape() -> None:
    assert len(SENTINEL_API_SECRET) == 43
    assert SENTINEL_API_KEY == "rlk_bss-app." + SENTINEL_API_SECRET


def test_configure_logging_can_send_logs_to_another_stream() -> None:
    import io

    from common.logging import configure_logging

    root = logging.getLogger()
    saved, level = root.handlers[:], root.level
    stream = io.StringIO()
    try:
        configure_logging("INFO", stream=stream)
        log_event(logging.getLogger("ratel.test"), logging.INFO, "stream.test", api_key_id="x")
    finally:
        root.handlers[:], root.level = saved, level
    assert json.loads(stream.getvalue())["event"] == "stream.test"
