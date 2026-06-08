from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from travel_agent.app.schemas.common import Location, Money, SourceRef, StrictBaseModel


class ProviderMetadata(StrictBaseModel):
    provider_name: str
    retrieved_at: datetime
    source_ref: SourceRef
    expires_at: datetime | None = None
    normalized_currency: str | None = None
    is_mock: bool = True


class FlightSearchRequest(StrictBaseModel):
    origin: str
    destination: str
    departure_date: date
    return_date: date | None = None
    travelers: int = 1
    currency: str = "KRW"
    outbound_departure_window: str | None = None
    return_departure_window: str | None = None


class FlightOption(StrictBaseModel):
    option_id: str
    airline: str
    origin: str
    destination: str
    departure_time: datetime
    arrival_time: datetime
    return_departure_time: datetime | None = None
    return_arrival_time: datetime | None = None
    price: Money
    refundable: bool = False
    booking_required: bool = True
    metadata: ProviderMetadata
    notes: list[str] = Field(default_factory=list)


class AccommodationSearchRequest(StrictBaseModel):
    destination: str
    check_in: date
    check_out: date
    travelers: int = 1
    currency: str = "KRW"
    preference: str | None = None


class AccommodationOption(StrictBaseModel):
    option_id: str
    name: str
    location: Location
    nightly_price: Money
    total_price: Money
    rating: float | None = None
    cancellation_policy: str = "Mock flexible policy; verify before booking."
    metadata: ProviderMetadata
    notes: list[str] = Field(default_factory=list)


class PlacesSearchRequest(StrictBaseModel):
    destination: str
    interests: list[str] = Field(default_factory=list)
    currency: str = "KRW"


class POIOption(StrictBaseModel):
    poi_id: str
    title: str
    type: str
    location: Location
    area: str
    estimated_cost: Money
    rating: float | None = None
    opening_hours: str | None = None
    recommended_duration_minutes: int = 90
    booking_required: bool = False
    metadata: ProviderMetadata
    notes: list[str] = Field(default_factory=list)


class RouteMatrixRequest(StrictBaseModel):
    locations: list[Location]
    departure_hint: datetime | None = None


class RouteLeg(StrictBaseModel):
    origin: str
    destination: str
    travel_minutes: int
    mode: str = "transit"
    distance_km: float | None = None
    metadata: ProviderMetadata


class VisaCheckRequest(StrictBaseModel):
    passport_country: str | None
    destination_country: str
    start_date: date | None = None
    end_date: date | None = None


class VisaCheckResult(StrictBaseModel):
    destination_country: str
    summary: str
    requires_official_verification: bool = True
    missing_required_info: list[str] = Field(default_factory=list)
    metadata: ProviderMetadata


class FxConversionRequest(StrictBaseModel):
    amount: float
    from_currency: str
    to_currency: str


class FxConversionResult(StrictBaseModel):
    amount: float
    from_currency: str
    converted_amount: float
    to_currency: str
    rate: float
    metadata: ProviderMetadata


class BookingRequest(StrictBaseModel):
    action_type: str
    payload: dict
    price: Money
    approval_id: str | None = None


class BookingProviderResult(StrictBaseModel):
    booking_id: str
    provider_reference: str
    simulated: bool = True
    status: str = "simulated_confirmed"
    metadata: ProviderMetadata
