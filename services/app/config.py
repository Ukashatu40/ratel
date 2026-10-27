from __future__ import annotations

from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    ratel_env: Literal["local", "test", "lab", "staging", "production"] = "local"
    log_level: str = "INFO"
    database_url: SecretStr = SecretStr("postgresql+psycopg://localhost/ratel_bss")
    redis_url: SecretStr = SecretStr("redis://127.0.0.1:6379/0")
    ratel_link_base_url: str = "http://127.0.0.1:4010"
    ratel_link_api_key: SecretStr | None = None
    # No default. Unset (or empty, or the CHANGE_ME placeholder) means the usage API refuses every
    # request, and outside local and test the app refuses to start (see app/main.py).
    meter_api_key: SecretStr | None = None
    # The key the reverse proxy adds to the public voucher redemption route, which RatelPay's page
    # calls without one (a browser cannot keep a secret). Same rules as meter_api_key.
    pay_api_key: SecretStr | None = None
    # The key the BSS routes require. Same rules as meter_api_key. TODO(auth, M-26): replace with
    # per-staff keys once the PRD decides the role model.
    bss_api_key: SecretStr | None = None

    @property
    def meter_api_key_value(self) -> str | None:
        """The configured usage API key, or None when it is unset, empty or the placeholder."""
        if self.meter_api_key is None:
            return None
        value = self.meter_api_key.get_secret_value().strip()
        return None if value in ("", "CHANGE_ME") else value

    @property
    def pay_api_key_value(self) -> str | None:
        """The configured redemption key, or None when it is unset, empty or the placeholder."""
        if self.pay_api_key is None:
            return None
        value = self.pay_api_key.get_secret_value().strip()
        return None if value in ("", "CHANGE_ME") else value

    @property
    def bss_api_key_value(self) -> str | None:
        """The configured BSS key, or None when it is unset, empty or the placeholder."""
        if self.bss_api_key is None:
            return None
        value = self.bss_api_key.get_secret_value().strip()
        return None if value in ("", "CHANGE_ME") else value
