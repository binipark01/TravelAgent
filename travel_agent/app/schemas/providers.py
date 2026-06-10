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
    star_rating: int | None = None
    review_count: int | None = None
    amenities: list[str] = Field(default_factory=list)
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
    # 구조화된 입국 요건(있을 때만 채운다)
    passport_country: str | None = None
    visa_required: bool | None = None
    visa_free_days: int | None = None
    entry_authorization: str | None = None  # 예: "전자여행허가 불필요", "ESTA 사전 승인 필요"
    passport_validity_rule: str | None = None  # 예: "입국 시 잔여 유효기간 6개월 이상 권장"
    details: list[str] = Field(default_factory=list)  # 화면에 보여줄 핵심 안내 항목
    source_url: str | None = None
    metadata: ProviderMetadata


class LocalTransportItem(StrictBaseModel):
    category: str  # "airport" | "pass"
    name: str
    detail: str | None = None
    price: str | None = None
    duration: str | None = None
    source_url: str | None = None


class LocalTransportPlan(StrictBaseModel):
    city: str
    summary: str
    airport_transfers: list[LocalTransportItem] = Field(default_factory=list)
    transit_passes: list[LocalTransportItem] = Field(default_factory=list)
    tips: list[str] = Field(default_factory=list)
    source_url: str | None = None
    metadata: ProviderMetadata


class EmergencyContact(StrictBaseModel):
    label: str  # 예: 경찰
    number: str  # 예: 110


class SafetyInfo(StrictBaseModel):
    destination_country: str
    summary: str
    emergency_contacts: list[EmergencyContact] = Field(default_factory=list)
    consular_call_center: str = "영사콜센터 +82-2-3210-0404 (24시간)"
    embassy_note: str | None = None
    travel_advisory: str | None = None  # 외교부 여행경보 안내
    insurance_tips: list[str] = Field(default_factory=list)
    local_cautions: list[str] = Field(default_factory=list)
    source_url: str | None = None
    metadata: ProviderMetadata


class NearbyDestination(StrictBaseModel):
    name: str  # 예: 오타루
    travel_time: str  # 예: JR 쾌속 약 35분
    transport: str  # 예: JR 쾌속 에어포트 / 직행버스
    highlights: list[str] = Field(default_factory=list)  # 운하, 오르골당
    best_for: str | None = None  # 예: 반나절~하루
    source_url: str | None = None


class NearbyGuide(StrictBaseModel):
    hub: str  # 기준 도시(삿포로)
    summary: str
    destinations: list[NearbyDestination] = Field(default_factory=list)
    source_url: str | None = None
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


class FxSample(StrictBaseModel):
    local_label: str  # 예: "10,000엔"
    krw_label: str  # 예: "약 93,000원"


class FxInfo(StrictBaseModel):
    base_currency: str  # 예: KRW
    target_currency: str  # 예: JPY
    target_per_base: float  # 1 KRW = ? target
    base_per_target: float  # 1 target = ? KRW (더 직관적)
    samples: list[FxSample] = Field(default_factory=list)
    budget_total_base: float | None = None
    budget_total_target: float | None = None
    budget_total_target_label: str | None = None
    tips: list[str] = Field(default_factory=list)
    source_url: str | None = None
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
