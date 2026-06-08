from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HttpClient:
    timeout_seconds: float = 10.0

    def get_json(self, url: str, *, headers: dict[str, str] | None = None) -> dict[str, Any]:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required for live connector calls") from exc
        response = httpx.get(url, headers=headers, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json()
