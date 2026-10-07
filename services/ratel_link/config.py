from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pymongo.uri_parser import parse_uri

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    ratel_env: Literal["local", "test", "lab", "staging", "production"] = "local"
    log_level: str = "INFO"
    mongo_uri: SecretStr = SecretStr("mongodb://127.0.0.1:27017")
    open5gs_db_name: str = "open5gs"
    ratel_link_db_name: str = "ratel_link"
    # File holding the key that encrypts Ki/OPc at rest. Never stored in MongoDB.
    ratel_link_key_file: Path | None = None

    @field_validator("mongo_uri")
    @classmethod
    def _localhost_only(cls, v: SecretStr) -> SecretStr:
        # Build Plan: only RatelLink touches MongoDB, and only over localhost.
        hosts = {host for host, _port in parse_uri(v.get_secret_value())["nodelist"]}
        if not hosts or not hosts <= _LOCAL_HOSTS:
            # Do not include the URI in the message: it may contain credentials.
            raise ValueError("MONGO_URI must point at 127.0.0.1/localhost only")
        return v
