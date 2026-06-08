from __future__ import annotations

from datetime import date

from travel_agent.app.connectors.accommodations.mock import MockAccommodationSearchConnector
from travel_agent.app.providers.mock_flights import MockFlightProvider
from travel_agent.app.schemas.providers import AccommodationSearchRequest, FlightSearchRequest


def test_flight_provider_returns_ranked_candidates() -> None:
    options = MockFlightProvider().search_flights(
        FlightSearchRequest(
            origin="서울",
            destination="Sapporo",
            departure_date=date(2026, 7, 3),
            return_date=date(2026, 7, 15),
            travelers=2,
            currency="KRW",
            outbound_departure_window="morning",
            return_departure_window="afternoon",
        )
    )

    assert len(options) == 3
    recommended = options[0]
    # 추천 옵션이 첫 번째이며 요청한 시간대를 반영한다.
    assert recommended.departure_time.hour == 9
    assert recommended.departure_time.minute == 30
    assert recommended.return_departure_time is not None
    assert recommended.return_departure_time.hour == 15

    prices = [option.price.amount for option in options]
    assert len(set(prices)) == 3
    # 인원수(2명)가 가격에 반영된다.
    assert recommended.price.amount == 520_000 * 2
    # 최저가 < 추천 < 프리미엄
    assert min(prices) < recommended.price.amount < max(prices)
    # 항공사명이 서로 다르고, 환불 가능 옵션이 최소 하나 있다.
    assert len({option.airline for option in options}) == 3
    assert any(option.refundable for option in options)
    assert all(option.price.currency == "KRW" for option in options)


def test_flight_provider_one_way_has_no_return_legs() -> None:
    options = MockFlightProvider().search_flights(
        FlightSearchRequest(
            origin="서울",
            destination="Tokyo",
            departure_date=date(2026, 9, 1),
            travelers=1,
            currency="KRW",
        )
    )

    assert options
    assert all(option.return_departure_time is None for option in options)
    assert all(option.return_arrival_time is None for option in options)


def _accommodation_items(preference: str | None) -> list[dict]:
    result = MockAccommodationSearchConnector().collect(
        AccommodationSearchRequest(
            destination="Tokyo",
            check_in=date(2026, 10, 3),
            check_out=date(2026, 10, 5),
            travelers=1,
            currency="KRW",
            preference=preference,
        )
    )
    return list(result.normalized_items)


def test_accommodation_connector_returns_three_tiers() -> None:
    items = _accommodation_items("hotel")

    assert len(items) == 3
    nights = 2
    for item in items:
        assert item["total_amount"] == item["nightly_amount"] * nights
    # 세 가격대가 서로 다르다.
    assert len({item["nightly_amount"] for item in items}) == 3


def test_accommodation_preference_orders_by_hint() -> None:
    budget_first = _accommodation_items("가성비 좋은 게스트하우스 위주")
    premium_first = _accommodation_items("프리미엄 고급 호텔로")
    default_order = _accommodation_items(None)

    assert budget_first[0]["nightly_amount"] == min(i["nightly_amount"] for i in budget_first)
    assert premium_first[0]["nightly_amount"] == max(i["nightly_amount"] for i in premium_first)
    # 선호가 없으면 스탠다드(가성비와 프리미엄의 중간 가격)가 먼저 온다.
    nightly_values = sorted(i["nightly_amount"] for i in default_order)
    assert default_order[0]["nightly_amount"] == nightly_values[1]
