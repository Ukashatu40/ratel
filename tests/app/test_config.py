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
