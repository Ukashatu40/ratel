"""Structured JSON logging with redaction of sensitive fields.

Rules (docs/LOGGING_AND_OBSERVABILITY.md):
- One JSON object per line.
- `event` is a dotted, stable name such as `line.activate.succeeded`.
- Sensitive keys are replaced with [REDACTED]. Cards and PINs are masked to last four digits.
- Redaction is by key name. It cannot catch a secret pasted into a free-text message,
  so never put values in messages. Pass fields instead.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, TextIO

REDACTED = "[REDACTED]"

# Matched case-insensitively on the key name.
SENSITIVE_KEY_PARTS = (
    "ki",
    "opc",
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "encryption_key",
    "private_key",
    "pin",
    "nin",
    "id_number",
    "mongo_uri",
    "database_url",
    "redis_url",
    "bearer",
    "key_hash",
    "secret_hash",
    "ciphertext",
    "plaintext",
)
# Exact names that contain a sensitive part but are safe and needed in logs. Checked first.
# An api_key_id is an internal label for a calling system, not a credential.
_ALLOWED_EXACT = frozenset({"api_key_id", "api_key_generation"})
# Short parts match only whole snake_case words, so "kind" and "pinned" are not redacted.
_WORD_ONLY = {"ki", "opc", "pin", "nin"}

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)

# Fields added to every log line of the current request (see bind_log_context). The HTTP
# middleware sets a fresh dict per request. It is a shared, mutable object on purpose: code that
# runs in a child task (route dependencies) updates it, and the middleware's own log line sees it.
log_context_var: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "log_context", default=None
)

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


def bind_log_context(**fields: Any) -> None:
    """Add fields to every log line of the current request. Does nothing outside a request."""
    context = log_context_var.get()
    if context is not None:
        context.update(fields)


def is_sensitive_key(key: str) -> bool:
    k = key.lower()
    if k in _ALLOWED_EXACT:
        return False
    words = set(k.replace("-", "_").split("_"))
    for part in SENSITIVE_KEY_PARTS:
        if part in _WORD_ONLY:
            if part in words:
                return True
        elif part in k:
            return True
    return False


def mask_last4(value: str) -> str:
    """Mask a card or PIN style number to its last four digits."""
    digits = str(value)
    if len(digits) <= 4:
        return "*" * len(digits)
    return "*" * (len(digits) - 4) + digits[-4:]


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: (REDACTED if isinstance(k, str) and is_sensitive_key(k) else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", None) or record.getMessage(),
        }
        rid = request_id_var.get()
        if rid:
            payload["request_id"] = rid
        context = log_context_var.get()
        if context:
            payload.update(redact(context))
        extras = {k: v for k, v in record.__dict__.items() if k not in _RESERVED and k != "event"}
        payload.update(redact(extras))
        if record.exc_info:
            # Type only. Exception text and tracebacks can contain sensitive values.
            payload["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure_logging(level: str = "INFO", stream: TextIO | None = None) -> None:
    """Install one JSON handler on the root logger. Idempotent; leaves other handlers alone.

    Logs go to stdout unless a stream is given. A command line tool that prints its result on
    stdout passes sys.stderr, so log lines never mix with the result.
    """
    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if not isinstance(h.formatter, JsonFormatter)]
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    """Preferred way to log: log_event(log, logging.INFO, "line.activate.succeeded", ...)."""
    logger.log(level, event, extra={"event": event, **fields})
