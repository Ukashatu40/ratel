"""HTTP client for RatelLink's /activate endpoint.

Reads base URL and API key from the environment (via Settings).
Local: point at the mock (http://127.0.0.1:4010).
Lab: point at the lab RatelLink.

The body matches contracts/openapi.yaml exactly: msisdn, speed_ul_mbps,
speed_dl_mbps, voice. No extra fields — the contract refuses them.
"""

from __future__ import annotations

import logging
from typing import Any, cast

import httpx

log = logging.getLogger("ratel.link.client")


class RatelLinkError(Exception):
    """RatelLink refused the request, or could not be reached."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class RatelLinkClient:
    def __init__(self, base_url: str, api_key: str, *, timeout: float = 5.0) -> None:
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def activate(
        self,
        imsi: str,
        *,
        msisdn: str,
        speed_ul_mbps: float,
        speed_dl_mbps: float,
        voice: bool,
        idempotency_key: str,
    ) -> None:
        """Send POST /v1/lines/{imsi}/activate. Raise RatelLinkError on failure."""
        url = f"{self._base}/v1/lines/{imsi}/activate"
        body = {
            "msisdn": msisdn,
            "speed_ul_mbps": speed_ul_mbps,
            "speed_dl_mbps": speed_dl_mbps,
            "voice": voice,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Idempotency-Key": idempotency_key,
        }
        try:
            response = httpx.post(url, json=body, headers=headers, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise RatelLinkError(f"activation request failed: {exc}") from exc

        if response.status_code == 200:
            return
        if response.status_code in (401, 404, 422, 503):
            raise RatelLinkError(
                f"RatelLink refused activation ({response.status_code})",
                status=response.status_code,
            )
        raise RatelLinkError(
            f"RatelLink returned unexpected status {response.status_code}",
            status=response.status_code,
        )

    def deactivate(self, imsi: str, *, reason: str, idempotency_key: str) -> None:
        """Send POST /v1/lines/{imsi}/deactivate. Raise RatelLinkError on failure."""
        url = f"{self._base}/v1/lines/{imsi}/deactivate"
        body = {"reason": reason}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Idempotency-Key": idempotency_key,
        }
        try:
            response = httpx.post(url, json=body, headers=headers, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise RatelLinkError(f"deactivate request failed: {exc}") from exc
        if response.status_code == 200:
            return
        if response.status_code in (401, 404, 422):
            raise RatelLinkError(
                f"RatelLink refused deactivation ({response.status_code})",
                status=response.status_code,
            )
        raise RatelLinkError(
            f"RatelLink returned unexpected status {response.status_code}",
            status=response.status_code,
        )

    def data(
        self,
        imsi: str,
        *,
        mode: str,
        speed_ul_mbps: float | None,
        speed_dl_mbps: float | None,
        idempotency_key: str,
    ) -> None:
        """Send POST /v1/lines/{imsi}/data. Raise RatelLinkError on failure."""
        url = f"{self._base}/v1/lines/{imsi}/data"
        body: dict[str, object] = {"mode": mode}
        if speed_ul_mbps is not None and speed_dl_mbps is not None:
            body["speed_ul_mbps"] = speed_ul_mbps
            body["speed_dl_mbps"] = speed_dl_mbps
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Idempotency-Key": idempotency_key,
        }
        try:
            response = httpx.post(url, json=body, headers=headers, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise RatelLinkError(f"data request failed: {exc}") from exc
        if response.status_code == 200:
            return
        if response.status_code in (401, 404, 409, 422):
            raise RatelLinkError(
                f"RatelLink refused data change ({response.status_code})",
                status=response.status_code,
            )
        raise RatelLinkError(
            f"RatelLink returned unexpected status {response.status_code}",
            status=response.status_code,
        )

    def get_line(self, imsi: str) -> dict[str, Any]:
        url = f"{self._base}/v1/lines/{imsi}"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            response = httpx.get(url, headers=headers, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise RatelLinkError(f"get_line failed: {exc}") from exc
        if response.status_code != 200:
            raise RatelLinkError(
                f"RatelLink returned {response.status_code}", status=response.status_code
            )
        return cast(dict[str, Any], response.json())
