import json
import logging

from common.logging import JsonFormatter, is_sensitive_key, log_event, mask_last4, redact
from tests.synthetic import SENTINEL_KI, SENTINEL_OPC


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
