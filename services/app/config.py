from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr
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
    # Paystack, the first payment gateway (decision 6; OPay after the demo). Payments stay switched
    # off, and their routes answer 503, until the key, the page to return to and the email domain
    # are all set. The key is a secret: only ever in the env file, never in Git or a log.
    paystack_secret_key: SecretStr | None = None
    paystack_base_url: str = "https://api.paystack.co"
    # Where Paystack sends the customer after paying: the RatelPay page.
    payment_callback_url: str | None = None
    # Paystack requires an email for every payment, and RatelPay shows nothing personal (TOP-2), so
    # each payment uses pay@<this domain> instead of the customer's own. TODO(PRD).
    payment_email_domain: str | None = None
    # TODO(PRD): sanity bounds, not product values.
    payment_min_kobo: int = Field(default=10_000, ge=1)
    payment_max_kobo: int = Field(default=100_000_000, ge=1)

    # The staff cookie is sent over HTTPS only. Off for local and test, where there is no TLS.
    staff_cookie_secure: bool = True
    # VAT in basis points (750 = 7.5%), recorded as its own ledger entry on every purchase.
    # TODO(finance): the rate is finance's to confirm (decision 7).
    vat_rate_bps: int = Field(default=750, ge=0, le=10_000)
    # Whether the rating job buys a line's plan again when its wallet covers it, so a top-up brings
    # data back by itself. TODO(PRD): a product decision, so it is off until the deployment says so.
    rating_auto_renew: bool = False

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
    def paystack_secret_key_value(self) -> str | None:
        """The Paystack key, or None when it is unset, empty or the placeholder."""
        if self.paystack_secret_key is None:
            return None
        value = self.paystack_secret_key.get_secret_value().strip()
        return None if value in ("", "CHANGE_ME") else value

    @property
    def payments_enabled(self) -> bool:
        return bool(
            self.paystack_secret_key_value
            and self.payment_callback_url
            and self.payment_email_domain
        )

    @property
    def payment_payer_email(self) -> str:
        return f"pay@{self.payment_email_domain}"
