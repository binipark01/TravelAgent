from __future__ import annotations

from travel_agent.app.schemas.common import SourceRef
from travel_agent.app.utils.time import utc_now


def stale_source_refs(refs: list[SourceRef]) -> list[SourceRef]:
    now = utc_now()
    return [ref for ref in refs if ref.expires_at and ref.expires_at < now]
