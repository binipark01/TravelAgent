from __future__ import annotations

from typing import Any

from travel_agent.app.connectors.base import ConnectorResult
from travel_agent.app.evidence.models import EvidenceSourceRef
from travel_agent.app.utils.ids import new_id


class MockConnector:
    source_type = "mock"

    def __init__(self, name: str, category: str) -> None:
        self.name = name
        self.category = category

    def collect(self, request: dict[str, Any]) -> ConnectorResult:
        return ConnectorResult(
            source_ref=EvidenceSourceRef(
                source_id=new_id("source"),
                provider=self.name,
                provider_ref=f"{self.name}:{self.category}",
                is_live=False,
                is_mock=True,
                source_type="mock",
                confidence=0.4,
                attribution="MVP mock connector",
                license_notes="Dev/test fallback only; not a live source.",
            ),
            raw_payload={"request": request, "mock": True},
            normalized_items=[],
        )
