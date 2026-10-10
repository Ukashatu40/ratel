from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pymongo.uri_parser import parse_uri

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

# Build Plan: "One API key per calling system, rotated every 90 days." No setting can raise this.
MAX_API_KEY_AGE_DAYS = 90


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    ratel_env: Literal["local", "test", "lab", "staging", "production"] = "local"
    log_level: str = "INFO"
    mongo_uri: SecretStr = SecretStr("mongodb://127.0.0.1:27017")
    open5gs_db_name: str = "open5gs"
    ratel_link_db_name: str = "ratel_link"
    # File holding the key that encrypts Ki/OPc at rest. Never stored in MongoDB. See ADR 0006.
    ratel_link_key_file: Path | None = None
    # Id of the key in that file. Stored in every envelope, so a later key can be told apart.
    ratel_link_key_id: str = Field(default="1", pattern=r"^[a-z0-9][a-z0-9._-]{0,31}$")
    # The pool of fixed addresses given to lines (Build Plan: 10.45.0.0/16 in the lab).
    ratel_link_ue_pool: str = "10.45.0.0/16"
    # API key lifetime rules. See ADR 0007.
    ratel_link_api_key_max_age_days: int = Field(default=90, ge=1, le=MAX_API_KEY_AGE_DAYS)
    ratel_link_api_key_rotation_overlap_days: int = Field(default=7, ge=1, le=30)
    ratel_link_api_key_expiry_warn_days: int = Field(default=14, ge=1, le=MAX_API_KEY_AGE_DAYS)

    @field_validator("mongo_uri")
    @classmethod
    def _localhost_only(cls, v: SecretStr) -> SecretStr:
        # Build Plan: only RatelLink touches MongoDB, and only over localhost.
        hosts = {host for host, _port in parse_uri(v.get_secret_value())["nodelist"]}
        if not hosts or not hosts <= _LOCAL_HOSTS:
            # Do not include the URI in the message: it may contain credentials.
            raise ValueError("MONGO_URI must point at 127.0.0.1/localhost only")
        return v

    @field_validator("ratel_link_ue_pool")
    @classmethod
    def _pool_is_a_private_ipv4_network(cls, v: str) -> str:
        net = ipaddress.ip_network(v, strict=True)
        if not isinstance(net, ipaddress.IPv4Network) or net.prefixlen > 30 or not net.is_private:
            raise ValueError(
                "RATEL_LINK_UE_POOL must be a private IPv4 network of at least 4 addresses"
            )
        return v

    @model_validator(mode="after")
    def _overlap_fits_in_key_lifetime(self) -> Settings:
        if self.ratel_link_api_key_rotation_overlap_days > self.ratel_link_api_key_max_age_days:
            raise ValueError("the rotation overlap cannot be longer than the API key lifetime")
        return self
