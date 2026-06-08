from __future__ import annotations

from typing import Any, Protocol

from pydantic import Field

from travel_agent.app.evidence.models import EvidenceSourceRef
from travel_agent.app.schemas.common import StrictBaseModel


class ConnectorResult(StrictBaseModel):
    source_ref: EvidenceSourceRef
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    normalized_items: list[dict[str, Any]] = Field(default_factory=list)


class SourceConnector(Protocol):
    name: str
    source_type: str

    def collect(self, request: StrictBaseModel | dict[str, Any]) -> ConnectorResult: ...
