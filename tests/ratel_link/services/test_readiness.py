"""Readiness: the store answers and the key is loaded, and the result names no detail."""

from __future__ import annotations

import logging

import pytest

from ratel_link.security.key_provider import NoKeyProvider
from ratel_link.services.readiness import ReadinessService
from tests.ratel_link.fakes import FakeStoreHealth, StaticKeyProvider


def test_ready_when_the_store_answers_and_the_key_is_loaded() -> None:
    result = ReadinessService(FakeStoreHealth(), StaticKeyProvider()).check()
    assert result.ready is True
    assert result.failed == ()


def test_not_ready_when_the_store_fails() -> None:
    store = FakeStoreHealth(ConnectionError("cannot reach the database"))
    result = ReadinessService(store, StaticKeyProvider()).check()
    assert result.ready is False
    assert result.failed == ("store",)


def test_not_ready_when_there_is_no_key() -> None:
    result = ReadinessService(FakeStoreHealth(), NoKeyProvider()).check()
    assert result.ready is False
    assert result.failed == ("key",)


def test_not_ready_when_the_current_key_id_has_no_key() -> None:
    # An id is configured but the key behind it is missing: still not usable.
    result = ReadinessService(FakeStoreHealth(), StaticKeyProvider(keys={}, current="1")).check()
    assert result.failed == ("key",)


def test_reports_every_part_that_failed() -> None:
    store = FakeStoreHealth(RuntimeError("boom"))
    result = ReadinessService(store, NoKeyProvider()).check()
    assert result.failed == ("store", "key")


def test_no_store_probe_counts_as_not_ready() -> None:
    # Nothing proves the database works, so the answer is "no", never "yes by default".
    result = ReadinessService(None, StaticKeyProvider()).check()
    assert result.ready is False
    assert result.failed == ("store",)


def test_the_log_names_the_component_and_the_exception_type_but_not_its_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_text = "mongodb://someuser:not-a-real-password@db-host:27017 timed out"
    caplog.set_level(logging.INFO)
    ReadinessService(FakeStoreHealth(ConnectionError(secret_text)), StaticKeyProvider()).check()
    events = [r.__dict__ for r in caplog.records if r.__dict__.get("event") == "readiness.failed"]
    assert len(events) == 1
    assert (events[0]["component"], events[0]["exc_type"]) == ("store", "ConnectionError")
    everything = caplog.text + repr(events)
    for fragment in ("someuser", "not-a-real-password", "db-host", "27017", "timed out"):
        assert fragment not in everything
