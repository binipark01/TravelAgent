from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel


def canonical_payload(payload: Any) -> str:
    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="json")
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def payload_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_payload(payload).encode("utf-8")).hexdigest()
