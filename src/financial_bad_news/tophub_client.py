"""Client for interacting with the TopHub search API."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping

import requests


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TophubClient:
    api_key: str | None = None
    base_url: str = "https://api.tophubdata.com"
    timeout: float = 20.0
    max_retries: int = 3
    backoff_base: float = 1.0
    backoff_cap: float = 30.0

    def search(self, keyword: str, page: int = 1, size: int = 50) -> MutableMapping[str, Any]:
        params = {"q": keyword, "p": page, "size": size}
        return self._call("/search", params)

    def _call(self, endpoint: str, params: Mapping[str, Any] | None = None) -> MutableMapping[str, Any]:
        url = f"{self.base_url}{endpoint}"
        headers = {"Authorization": self.api_key} if self.api_key else {}
        attempt = 0
        while True:
            try:
                response = requests.get(
                    url,
                    headers=headers,
                    params=dict(params) if params else None,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, MutableMapping):
                    raise RuntimeError("Unexpected response structure from TopHub")
                return payload
            except requests.RequestException as exc:
                if attempt >= self.max_retries:
                    raise
                delay = min(self.backoff_base * (2**attempt), self.backoff_cap)
                logger.warning(
                    "TopHub 请求失败（第 %s 次重试），将在 %s 秒后重试：%s",
                    attempt + 1,
                    delay,
                    exc,
                )
                time.sleep(delay)
                attempt += 1



__all__ = ["TophubClient"]
