"""HTTP client for RatelLink GET /v1/assignments with in-memory caching."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import SecretStr

from common.logging import log_event

log = logging.getLogger("ratel.meter.assignments")


class HttpAssignmentCache:
    """Refreshes and caches address-to-IMSI assignments from RatelLink."""

    def __init__(
        self,
        base_url: str,
        api_key: SecretStr | str,
        timeout: float = 5.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key if isinstance(api_key, SecretStr) else SecretStr(api_key)
        self._timeout = timeout
        self._client = client
        self._cache: dict[str, str] = {}

    def refresh(self) -> None:
        """Fetch GET /v1/assignments and replace the cache.

        Keeps the old cache on failure and never raises out of this method.
        """
        url = f"{self._base_url}/v1/assignments"
        headers = {
            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
            "Accept": "application/json",
        }

        try:
            if self._client is not None:
                response = self._client.get(url, headers=headers, timeout=self._timeout)
            else:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.get(url, headers=headers)

            if response.status_code != 200:
                log_event(
                    log,
                    logging.WARNING,
                    "meter.assignments.refresh_failed",
                    status_code=response.status_code,
                )
                return

            data: Any = response.json()
            if not isinstance(data, dict) or "assignments" not in data:
                log_event(
                    log,
                    logging.WARNING,
                    "meter.assignments.malformed_response",
                )
                return

            assignments = data.get("assignments")
            if not isinstance(assignments, list):
                log_event(
                    log,
                    logging.WARNING,
                    "meter.assignments.malformed_response",
                )
                return

            new_cache: dict[str, str] = {}
            for item in assignments:
                if isinstance(item, dict) and "ue_ip" in item and "imsi" in item:
                    ue_ip = item["ue_ip"]
                    imsi = item["imsi"]
                    if isinstance(ue_ip, str) and isinstance(imsi, str):
                        new_cache[ue_ip] = imsi

            self._cache = new_cache
            log_event(
                log,
                logging.INFO,
                "meter.assignments.refreshed",
                count=len(self._cache),
            )
        except Exception as exc:
            # Never log the key or full exception with sensitive query/headers
            log_event(
                log,
                logging.WARNING,
                "meter.assignments.error",
                error_type=type(exc).__name__,
            )

    def imsi_for(self, ue_ip: str) -> str | None:
        """Return the IMSI mapped to ue_ip, or None if unknown."""
        return self._cache.get(ue_ip)
