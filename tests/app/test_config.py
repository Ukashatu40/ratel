import pytest

from app.config import Settings


def test_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATEL_ENV", "lab")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:SENTINEL@127.0.0.1/db")
    s = Settings()
    assert s.ratel_env == "lab"
    assert "SENTINEL" not in repr(s)  # secrets never appear in repr or logs


def test_unknown_environment_name_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATEL_ENV", "prod")
    with pytest.raises(ValueError):
        Settings()


def test_call_charging_is_off_until_a_start_with_its_utc_offset_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CALL_CHARGING_FROM", raising=False)
    assert Settings().call_charging_from is None
    monkeypatch.setenv("CALL_CHARGING_FROM", "")  # as the templates ship it
    assert Settings().call_charging_from is None
    monkeypatch.setenv("CALL_CHARGING_FROM", "2026-11-25T13:00:00+01:00")
    start = Settings().call_charging_from
    assert start is not None and start.utcoffset() is not None
    assert start.isoformat() == "2026-11-25T13:00:00+01:00"
    monkeypatch.setenv("CALL_CHARGING_FROM", "2026-11-25T12:00:00")  # no offset: refused
    with pytest.raises(ValueError):
        Settings()
