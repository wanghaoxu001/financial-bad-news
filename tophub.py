"""Simple TopHub client example kept for reference."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, MutableMapping

import requests


@dataclass(slots=True)
class Tophub:
    api_key: str = ""
    base_url: str = "https://api.tophubdata.com"

    def nodes(self, page: int = 1) -> MutableMapping[str, Any]:
        return self._call("/nodes", {"p": page})

    def node(self, hashid: str) -> MutableMapping[str, Any]:
        return self._call(f"/nodes/{hashid}")

    def node_history(self, hashid: str, date: str) -> MutableMapping[str, Any]:
        return self._call(f"/nodes/{hashid}/historys", {"date": date})

    def search(self, keyword: str, page: int = 1, size: int = 50) -> MutableMapping[str, Any]:
        params = {"q": keyword, "p": page, "size": size}
        return self._call("/search", params)

    def _call(self, endpoint: str, params: Mapping[str, Any] | None = None) -> MutableMapping[str, Any]:
        url = f"{self.base_url}{endpoint}"
        if params:
            query = "&".join(f"{key}={value}" for key, value in params.items())
            url = f"{url}?{query}"
        headers: Dict[str, str] = {"Authorization": self.api_key} if self.api_key else {}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, MutableMapping):
            raise RuntimeError("Unexpected response structure")
        return payload


if __name__ == "__main__":
    client = Tophub("<your-api-key>")
    data = client.search("银行", page=1)
    print(data)
