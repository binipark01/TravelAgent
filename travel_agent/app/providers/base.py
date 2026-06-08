from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from travel_agent.app.schemas.providers import (
    AccommodationOption,
    AccommodationSearchRequest,
    BookingProviderResult,
    BookingRequest,
    FlightOption,
    FlightSearchRequest,
    FxConversionRequest,
    FxConversionResult,
    PlacesSearchRequest,
    POIOption,
    RouteLeg,
    RouteMatrixRequest,
    VisaCheckRequest,
    VisaCheckResult,
)


class FlightProvider(Protocol):
    def search_flights(self, request: FlightSearchRequest) -> list[FlightOption]: ...


class AccommodationProvider(Protocol):
    def search_accommodations(
        self, request: AccommodationSearchRequest
    ) -> list[AccommodationOption]: ...


class PlacesProvider(Protocol):
    def search_pois(self, request: PlacesSearchRequest) -> list[POIOption]: ...


class RoutesProvider(Protocol):
    def compute_route_matrix(self, request: RouteMatrixRequest) -> list[RouteLeg]: ...


class VisaProvider(Protocol):
    def check_entry_requirements(self, request: VisaCheckRequest) -> VisaCheckResult: ...


class WeatherProvider(Protocol):
    def get_weather_summary(self, destination: str) -> str: ...


class FxProvider(Protocol):
    def convert(self, request: FxConversionRequest) -> FxConversionResult: ...


class BookingProvider(Protocol):
    def create_booking_stub(self, request: BookingRequest) -> BookingProviderResult: ...


@dataclass(frozen=True)
class ProviderBundle:
    flights: FlightProvider
    accommodations: AccommodationProvider
    places: PlacesProvider
    routes: RoutesProvider
    visa: VisaProvider
    weather: WeatherProvider
    fx: FxProvider
    booking: BookingProvider


def build_mock_provider_bundle() -> ProviderBundle:
    from travel_agent.app.providers.mock_accommodation import MockAccommodationProvider
    from travel_agent.app.providers.mock_booking import MockBookingProvider
    from travel_agent.app.providers.mock_flights import MockFlightProvider
    from travel_agent.app.providers.mock_fx import MockFxProvider
    from travel_agent.app.providers.mock_places import MockPlacesProvider
    from travel_agent.app.providers.mock_routes import MockRoutesProvider
    from travel_agent.app.providers.mock_visa import MockVisaProvider
    from travel_agent.app.providers.mock_weather import MockWeatherProvider

    return ProviderBundle(
        flights=MockFlightProvider(),
        accommodations=MockAccommodationProvider(),
        places=MockPlacesProvider(),
        routes=MockRoutesProvider(),
        visa=MockVisaProvider(),
        weather=MockWeatherProvider(),
        fx=MockFxProvider(),
        booking=MockBookingProvider(),
    )
