"""Low-level HTTP client for Civitai's tRPC and REST APIs."""

import json
from typing import Any
from urllib.parse import urlencode

import requests

_DOMAINS = {
    "green": "https://civitai.com",   # domaine principal (bounties désactivés)
    "red":   "https://civitai.red",   # domaine NSFW (bounties actifs)
}
_REST_BASE = "https://civitai.com/api/v1"


class CivitaiError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class CivitaiClient:
    """
    Wraps Civitai's REST v1 and internal tRPC endpoints.

    Authentication is optional for public read endpoints but required for
    anything that touches your account data.

    Get your API token at: https://civitai.com/user/account
    """

    def __init__(
        self,
        api_token: str | None = None,
        timeout: int = 30,
        domain: str = "red",
    ):
        base = _DOMAINS.get(domain, domain)  # accepte aussi une URL complète
        self._trpc_base = f"{base}/api/trpc"
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "civitai-python/0.1",
        })
        if api_token:
            self._session.headers["Authorization"] = f"Bearer {api_token}"
        self.timeout = timeout

    # ------------------------------------------------------------------
    # tRPC helpers
    # ------------------------------------------------------------------

    def _trpc_get(self, procedure: str, input_data: Any) -> Any:
        """Call a tRPC query procedure via GET."""
        encoded = urlencode({"input": json.dumps({"json": input_data})})
        url = f"{self._trpc_base}/{procedure}?{encoded}"
        resp = self._session.get(url, timeout=self.timeout)
        return self._parse_trpc(resp, procedure)

    def _trpc_batch_get(self, procedures: list[tuple[str, Any]]) -> list[Any]:
        """Call multiple tRPC query procedures in one request."""
        inputs = {str(i): {"json": data} for i, (_, data) in enumerate(procedures)}
        names = ",".join(p for p, _ in procedures)
        params = urlencode({"batch": 1, "input": json.dumps(inputs)})
        url = f"{self._trpc_base}/{names}?{params}"
        resp = self._session.get(url, timeout=self.timeout)
        self._raise_for_status(resp)
        results = resp.json()
        return [self._unwrap_trpc_result(r, procedures[i][0]) for i, r in enumerate(results)]

    def _parse_trpc(self, resp: requests.Response, procedure: str) -> Any:
        self._raise_for_status(resp)
        envelope = resp.json()
        return self._unwrap_trpc_result(envelope, procedure)

    @staticmethod
    def _unwrap_trpc_result(envelope: Any, procedure: str) -> Any:
        if isinstance(envelope, list):
            envelope = envelope[0]
        if "error" in envelope:
            err = envelope["error"]
            msg = err.get("message") or err.get("json", {}).get("message", "Unknown tRPC error")
            raise CivitaiError(f"{procedure}: {msg}")
        return envelope["result"]["data"]["json"]

    @staticmethod
    def _raise_for_status(resp: requests.Response) -> None:
        if resp.status_code in (401, 403):
            raise CivitaiError(
                "Access denied — the bounty endpoints require a valid API token. "
                "Generate one at https://civitai.com/user/account",
                resp.status_code,
            )
        if resp.status_code == 429:
            raise CivitaiError("Rate limit exceeded. Wait before retrying.", 429)
        if not resp.ok:
            raise CivitaiError(f"HTTP {resp.status_code}: {resp.text[:200]}", resp.status_code)

    # ------------------------------------------------------------------
    # REST v1 helpers
    # ------------------------------------------------------------------

    def _rest_get(self, path: str, params: dict | None = None) -> Any:
        url = f"{_REST_BASE}/{path.lstrip('/')}"
        resp = self._session.get(url, params=params, timeout=self.timeout)
        self._raise_for_status(resp)
        return resp.json()
