from dataclasses import dataclass


@dataclass(frozen=True)
class SourceCandidate:
    domain: str
    name: str
    source_type: str
    connector: str
    status: str
    required_env: tuple[str, ...] = ()


def candidate(
    domain: str,
    name: str,
    source_type: str,
    connector: str,
    status: str,
    required_env: tuple[str, ...] = (),
) -> SourceCandidate:
    return SourceCandidate(domain, name, source_type, connector, status, required_env)


CATALOG: dict[str, tuple[SourceCandidate, ...]] = {
    "flights": (
        candidate(
            "flights",
            "amadeus",
            "official_api",
            "AmadeusFlightConnector",
            "enabled_when_configured",
            ("AMADEUS_CLIENT_ID", "AMADEUS_CLIENT_SECRET"),
        ),
        candidate(
            "flights",
            "skyscanner",
            "partner_api",
            "SkyscannerFlightConnector",
            "requires_partner_access",
            ("SKYSCANNER_API_KEY",),
        ),
        candidate(
            "flights",
            "naver_flight",
            "authorized_only",
            "NaverFlightConnector",
            "disabled_until_authorized",
            ("NAVER_FLIGHT_AUTH_MODE",),
        ),
        candidate(
            "flights",
            "google_flights",
            "public_page",
            "GoogleFlightsPublicPageConnector",
            "enabled_by_default",
        ),
        candidate("flights", "mock", "mock", "MockFlightConnector", "dev_test_only"),
    ),
    "accommodations": (
        candidate(
            "accommodations",
            "expedia_rapid",
            "partner_api",
            "ExpediaRapidAccommodationConnector",
            "requires_partner_access",
            ("EXPEDIA_RAPID_API_KEY", "EXPEDIA_RAPID_SHARED_SECRET"),
        ),
        candidate(
            "accommodations",
            "hotelbeds",
            "partner_api",
            "HotelbedsAccommodationConnector",
            "enabled_when_configured",
            ("HOTELBEDS_API_KEY", "HOTELBEDS_SECRET"),
        ),
        candidate(
            "accommodations",
            "booking_demand",
            "partner_api",
            "BookingDemandAccommodationConnector",
            "requires_affiliate_access",
            ("BOOKING_DEMAND_TOKEN",),
        ),
        candidate(
            "accommodations",
            "agoda_partner",
            "partner_api",
            "AgodaPartnerAccommodationConnector",
            "requires_partner_access",
            ("AGODA_PARTNER_API_KEY", "AGODA_SITE_ID"),
        ),
        candidate(
            "accommodations",
            "google_hotels_partner",
            "official_api",
            "GoogleHotelsTravelPartnerConnector",
            "enabled_when_configured",
            ("GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_HOTELS_PARTNER_ACCOUNT"),
        ),
        candidate(
            "accommodations",
            "airbnb_public_page",
            "public_page",
            "AirbnbPublicPageAccommodationConnector",
            "disabled_until_authorized",
            ("AIRBNB_AUTHORIZATION_MODE",),
        ),
        candidate(
            "accommodations",
            "mock",
            "mock",
            "MockAccommodationConnector",
            "dev_test_only",
        ),
    ),
    "places": (
        candidate(
            "places",
            "google_places",
            "official_api",
            "GooglePlacesConnector",
            "enabled_when_configured",
            ("GOOGLE_MAPS_API_KEY",),
        ),
        candidate(
            "places",
            "kakao_local",
            "official_api",
            "KakaoLocalConnector",
            "enabled_when_configured",
            ("KAKAO_REST_API_KEY",),
        ),
        candidate(
            "places",
            "kto_tourapi",
            "official_api",
            "KtoTourApiConnector",
            "enabled_when_configured",
            ("KTO_TOUR_API_KEY",),
        ),
        candidate("places", "mock", "mock", "MockPlacesConnector", "dev_test_only"),
    ),
    "routes": (
        candidate(
            "routes",
            "google_routes",
            "official_api",
            "GoogleRoutesConnector",
            "enabled_when_configured",
            ("GOOGLE_MAPS_API_KEY",),
        ),
        candidate(
            "routes",
            "naver_directions",
            "official_api",
            "NaverDirectionsConnector",
            "enabled_when_configured",
            ("NAVER_MAPS_CLIENT_ID", "NAVER_MAPS_CLIENT_SECRET"),
        ),
        candidate(
            "routes",
            "kakao_mobility",
            "official_api",
            "KakaoMobilityConnector",
            "enabled_when_configured",
            ("KAKAO_MOBILITY_API_KEY",),
        ),
        candidate("routes", "mock", "mock", "MockRoutesConnector", "dev_test_only"),
    ),
    "activities": (
        candidate(
            "activities",
            "viator",
            "partner_api",
            "ViatorActivityConnector",
            "requires_partner_access",
            ("VIATOR_API_KEY",),
        ),
        candidate(
            "activities",
            "getyourguide",
            "partner_api",
            "GetYourGuideActivityConnector",
            "requires_partner_access",
            ("GETYOURGUIDE_API_KEY",),
        ),
        candidate("activities", "mock", "mock", "MockActivityConnector", "dev_test_only"),
    ),
    "visa": (
        candidate(
            "visa",
            "sherpa",
            "partner_api",
            "SherpaVisaConnector",
            "requires_partner_access",
            ("SHERPA_API_KEY",),
        ),
        candidate(
            "visa",
            "timatic",
            "partner_api",
            "TimaticVisaConnector",
            "requires_partner_access",
            ("TIMATIC_API_KEY",),
        ),
        candidate("visa", "mock", "mock", "MockVisaConnector", "dev_test_only"),
    ),
    "safety": (
        candidate(
            "safety",
            "mofa",
            "official_api",
            "MofaSafetyConnector",
            "enabled_when_configured",
            ("MOFA_API_KEY",),
        ),
        candidate("safety", "mock", "mock", "MockSafetyConnector", "dev_test_only"),
    ),
    "weather": (
        candidate(
            "weather",
            "open_meteo",
            "official_api",
            "OpenMeteoWeatherConnector",
            "enabled_by_default",
        ),
        candidate(
            "weather",
            "openweather",
            "official_api",
            "OpenWeatherConnector",
            "enabled_when_configured",
            ("OPENWEATHER_API_KEY",),
        ),
        candidate("weather", "mock", "mock", "MockWeatherConnector", "dev_test_only"),
    ),
    "fx": (
        candidate(
            "fx",
            "frankfurter",
            "official_api",
            "FrankfurterFxConnector",
            "enabled_by_default",
        ),
        candidate(
            "fx",
            "open_exchange_rates",
            "official_api",
            "OpenExchangeRatesConnector",
            "enabled_when_configured",
            ("OPEN_EXCHANGE_RATES_APP_ID",),
        ),
        candidate("fx", "mock", "mock", "MockFxConnector", "dev_test_only"),
    ),
}
