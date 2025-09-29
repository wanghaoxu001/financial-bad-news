"""Client for interacting with the TopHub search API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping

import requests


@dataclass(slots=True)
class TophubClient:
    api_key: str | None = None
    base_url: str = "https://api.tophubdata.com"
    timeout: float = 10.0

    def search(self, keyword: str, page: int = 1, size: int = 50) -> MutableMapping[str, Any]:
        params = {"q": keyword, "p": page, "size": size}
        return self._call("/search", params)

    def _call(self, endpoint: str, params: Mapping[str, Any] | None = None) -> MutableMapping[str, Any]:
        url = f"{self.base_url}{endpoint}"
        if params:
            query = "&".join(f"{key}={value}" for key, value in params.items())
            url = f"{url}?{query}"
        headers = {"Authorization": self.api_key} if self.api_key else {}
        response = requests.get(url, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, MutableMapping):
            raise RuntimeError("Unexpected response structure from TopHub")
        return payload


__all__ = ["TophubClient"]

