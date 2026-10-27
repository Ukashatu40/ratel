"""HTTP poster for delivering usage batches to the RatelMeter API."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx
from pydantic import SecretStr

from common.logging import log_event

log = logging.getLogger("ratel.meter.poster")


class HttpMeterPoster:
    """Posts usage record batches to POST /v1/usage on the RatelMeter API."""

    def __init__(
        self,
        base_url: str,
        api_key: SecretStr | str,
        timeout: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key if isinstance(api_key, SecretStr) else SecretStr(api_key)
        self._timeout = timeout
        self._client = client

    def __call__(self, batch: object) -> bool:
        """POST a batch of usage records. Returns True only on success."""
        if not batch:
            return True

        if isinstance(batch, list):
            payload: dict[str, Any] = {"records": batch}
            record_count = len(batch)
        elif isinstance(batch, dict) and "records" in batch:
            payload = batch
            records_val = batch.get("records")
            record_count = len(records_val) if isinstance(records_val, list) else 1
        else:
            log_event(
                log,
                logging.ERROR,
                "meter.poster.invalid_payload_type",
                type=type(batch).__name__,
            )
            return False

        url = f"{self._base_url}/v1/usage"
        headers = {
            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
            "Content-Type": "application/json",
            "Idempotency-Key": str(uuid.uuid4()),
        }

        try:
            if self._client is not None:
                response = self._client.post(
                    url, json=payload, headers=headers, timeout=self._timeout
                )
            else:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.post(url, json=payload, headers=headers)

            if response.status_code in (200, 204):
                log_event(
                    log,
                    logging.INFO,
                    "meter.poster.success",
                    record_count=record_count,
                )
                return True

            log_event(
                log,
                logging.WARNING,
                "meter.poster.rejected",
                status_code=response.status_code,
                record_count=record_count,
            )
            return False
        except Exception as exc:
            # Never log the key, IMSIs, or exception messages containing payloads
            log_event(
                log,
                logging.WARNING,
                "meter.poster.error",
                error_type=type(exc).__name__,
                record_count=record_count,
            )
            return False
