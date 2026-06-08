from __future__ import annotations

from collections.abc import Callable
from typing import Final

from travel_agent.app.connectors.accommodations.base import AccommodationConnector
from travel_agent.app.connectors.accommodations.external import (
    ExternalAccommodationSearchConnector,
)
from travel_agent.app.connectors.accommodations.mock import MockAccommodationSearchConnector
from travel_agent.app.sources.catalog import SourceCandidate

ConnectorFactory = Callable[[SourceCandidate], AccommodationConnector]


def _mock_connector(source: SourceCandidate) -> AccommodationConnector:
    return MockAccommodationSearchConnector()


def _external_connector(source: SourceCandidate) -> AccommodationConnector:
    return ExternalAccommodationSearchConnector(source)


CONNECTOR_FACTORIES: Final[dict[str, ConnectorFactory]] = {
    "expedia_rapid": _external_connector,
    "hotelbeds": _external_connector,
    "booking_demand": _external_connector,
    "agoda_partner": _external_connector,
    "google_hotels_partner": _external_connector,
    "airbnb_public_page": _external_connector,
    "mock": _mock_connector,
}


def build_accommodation_connector(source: SourceCandidate) -> AccommodationConnector | None:
    factory = CONNECTOR_FACTORIES.get(source.name)
    if factory is None:
        return None
    return factory(source)


def MockAccommodationConnector() -> AccommodationConnector:
    return MockAccommodationSearchConnector()


def ExpediaRapidAccommodationConnector() -> AccommodationConnector:
    return ExternalAccommodationSearchConnector(
        SourceCandidate(
            "accommodations",
            "expedia_rapid",
            "partner_api",
            "ExpediaRapidAccommodationConnector",
            "requires_partner_access",
        )
    )


def HotelbedsAccommodationConnector() -> AccommodationConnector:
    return ExternalAccommodationSearchConnector(
        SourceCandidate(
            "accommodations",
            "hotelbeds",
            "partner_api",
            "HotelbedsAccommodationConnector",
            "enabled_when_configured",
        )
    )


def BookingDemandAccommodationConnector() -> AccommodationConnector:
    return ExternalAccommodationSearchConnector(
        SourceCandidate(
            "accommodations",
            "booking_demand",
            "partner_api",
            "BookingDemandAccommodationConnector",
            "requires_affiliate_access",
        )
    )


def AgodaPartnerAccommodationConnector() -> AccommodationConnector:
    return ExternalAccommodationSearchConnector(
        SourceCandidate(
            "accommodations",
            "agoda_partner",
            "partner_api",
            "AgodaPartnerAccommodationConnector",
            "requires_partner_access",
        )
    )


def GoogleHotelsTravelPartnerConnector() -> AccommodationConnector:
    return ExternalAccommodationSearchConnector(
        SourceCandidate(
            "accommodations",
            "google_hotels_partner",
            "official_api",
            "GoogleHotelsTravelPartnerConnector",
            "enabled_when_configured",
        )
    )


def AirbnbPublicPageAccommodationConnector() -> AccommodationConnector:
    return ExternalAccommodationSearchConnector(
        SourceCandidate(
            "accommodations",
            "airbnb_public_page",
            "public_page",
            "AirbnbPublicPageAccommodationConnector",
            "disabled_until_authorized",
        )
    )
