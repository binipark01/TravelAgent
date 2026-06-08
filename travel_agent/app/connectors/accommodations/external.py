from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from travel_agent.app.connectors.base import ConnectorResult
from travel_agent.app.connectors.errors import ProviderConfigurationError
from travel_agent.app.schemas.providers import AccommodationSearchRequest
from travel_agent.app.sources.catalog import SourceCandidate

SOURCE_NOTES: Final[dict[str, str]] = {
    "expedia_rapid": "Partner API boundary registered; live mapping is not enabled in MVP.",
    "hotelbeds": "Partner API boundary registered; live mapping is not enabled in MVP.",
    "booking_demand": "Booking.com Demand API boundary registered for affiliate access.",
    "agoda_partner": (
        "Agoda partner API boundary registered; public GraphQL collection is not used."
    ),
    "google_hotels_partner": (
        "Google Travel Partner API is for Hotel Center account diagnostics, not open search."
    ),
    "airbnb_public_page": "Airbnb public page automation requires explicit authorization.",
}


@dataclass(frozen=True)
class ExternalAccommodationSearchConnector:
    source: SourceCandidate

    @property
    def name(self) -> str:
        return self.source.name

    @property
    def source_type(self) -> str:
        return self.source.source_type

    def collect(self, request: AccommodationSearchRequest) -> ConnectorResult:
        note = SOURCE_NOTES.get(self.source.name, "External accommodation source registered.")
        raise ProviderConfigurationError(
            f"{self.source.name} accommodation connector is registered but "
            f"live collection is not implemented. {note}"
        )
