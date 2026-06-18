from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from travel_agent.app.config import Settings
from travel_agent.app.schemas.providers import AccommodationSearchRequest
from travel_agent.app.sources.registry import SourceRegistry
from travel_agent.app.tools.accommodation_search import AccommodationSearchTool

ACCOMMODATION_SOURCES = (
    "booking_demand",
    "agoda_partner",
    "airbnb_public_page",
    "google_hotels_partner",
    "mock",
)


def test_accommodation_source_policy_exposes_booking_agoda_airbnb_google(
    monkeypatch,
) -> None:
    for env_name in (
        "BOOKING_DEMAND_TOKEN",
        "AGODA_PARTNER_API_KEY",
        "AGODA_SITE_ID",
        "AIRBNB_AUTHORIZATION_MODE",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_HOTELS_PARTNER_ACCOUNT",
    ):
        monkeypatch.delenv(env_name, raising=False)
    registry = SourceRegistry(
        Settings(
            enable_live_providers=False,
            provider_fallback_to_mock=True,
            accommodation_sources=ACCOMMODATION_SOURCES,
        )
    )

    statuses = {
        item["name"]: item for item in registry.status_for_domain("accommodations")
    }

    assert set(ACCOMMODATION_SOURCES) <= set(statuses)
    assert statuses["booking_demand"]["enabled"] is False
    assert statuses["agoda_partner"]["enabled"] is False
    assert statuses["google_hotels_partner"]["enabled"] is False
    assert statuses["airbnb_public_page"]["enabled"] is False
    assert statuses["airbnb_public_page"]["reason"] == "source requires explicit authorization"
    assert statuses["mock"]["enabled"] is True


def test_accommodation_policy_blocks_external_sources_when_live_disabled(
    monkeypatch,
) -> None:
    monkeypatch.setenv("BOOKING_DEMAND_TOKEN", "test-token")
    monkeypatch.setenv("AGODA_PARTNER_API_KEY", "test-agoda-key")
    monkeypatch.setenv("AGODA_SITE_ID", "test-site")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "test-credentials.json")
    monkeypatch.setenv("GOOGLE_HOTELS_PARTNER_ACCOUNT", "test-account")
    registry = SourceRegistry(
        Settings(
            enable_live_providers=False,
            provider_fallback_to_mock=True,
            accommodation_sources=ACCOMMODATION_SOURCES,
        )
    )

    statuses = {
        item["name"]: item for item in registry.status_for_domain("accommodations")
    }

    assert statuses["booking_demand"]["reason"] == "live providers disabled"
    assert statuses["agoda_partner"]["reason"] == "live providers disabled"
    assert statuses["google_hotels_partner"]["reason"] == "live providers disabled"
    assert statuses["mock"]["enabled"] is True


def test_accommodation_search_tool_uses_mock_fallback_without_live_network() -> None:
    tool = AccommodationSearchTool(
        Settings(
            enable_live_providers=False,
            provider_fallback_to_mock=True,
            accommodation_sources=ACCOMMODATION_SOURCES,
        )
    )
    request = AccommodationSearchRequest(
        destination="Osaka",
        check_in=date(2026, 10, 3),
        check_out=date(2026, 10, 7),
        travelers=2,
        currency="KRW",
        preference="hotel",
    )

    options = tool.search(request)

    assert len(options) == 3
    for option in options:
        assert option.metadata.provider_name == "mock_accommodation"
        assert option.metadata.source_ref.provider == "mock_accommodation"
        assert option.metadata.source_ref.is_mock is True
        assert option.metadata.source_ref.is_live is False
        assert option.total_price.amount == option.nightly_price.amount * 4
    # 가성비/스탠다드/프리미엄 세 가격대가 제공된다.
    assert len({option.nightly_price.amount for option in options}) == 3


def test_agent_run_records_accommodation_source_candidates(
    client: TestClient, base_trip_payload: dict
) -> None:
    created = client.post("/agent/runs", json=base_trip_payload).json()

    response = client.post(
        f"/agent/runs/{created['run_id']}/messages",
        json={
            "message": (
                "출발지는 서울, 2026-10-03부터 2026-10-07까지, "
                "여권 국적은 대한민국, 성인 2명"
            )
        },
    )

    assert response.status_code == 200
    events = response.json()["events"]
    rejected_sources = {
        event["payload"]["source"]
        for event in events
        if event["type"] == "source_rejected"
        and event["payload"]["domain"] == "accommodations"
    }
    discovered_sources = {
        source
        for event in events
        if event["type"] == "source_discovered"
        and event["payload"]["domain"] == "accommodations"
        for source in event["payload"]["sources"]
    }

    assert {"booking_demand", "agoda_partner", "google_hotels_partner"} <= rejected_sources
    assert "airbnb_public_page" in rejected_sources
    assert "mock" in discovered_sources


def test_hotel_booking_url_includes_trip_dates() -> None:
    from travel_agent.app.connectors.accommodations.google_hotel_browser import (
        build_hotel_booking_url,
    )

    dated = build_hotel_booking_url("삿포로 그랑벨 호텔", date(2026, 6, 19), date(2026, 6, 22))
    # 예약 링크에 여행 날짜가 들어가 오늘이 아닌 체크인/체크아웃으로 열린다.
    assert "2026" in dated
    assert "6%EC%9B%94+19%EC%9D%BC" in dated  # '6월 19일'
    assert "6%EC%9B%94+22%EC%9D%BC" in dated  # '6월 22일'

    undated = build_hotel_booking_url("삿포로 그랑벨 호텔")
    assert "2026" not in undated
