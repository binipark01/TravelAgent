from __future__ import annotations

from typing import Protocol

from travel_agent.app.connectors.base import ConnectorResult
from travel_agent.app.schemas.providers import AccommodationSearchRequest


class AccommodationConnector(Protocol):
    name: str
    source_type: str

    def collect(self, request: AccommodationSearchRequest) -> ConnectorResult: ...
