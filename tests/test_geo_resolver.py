from __future__ import annotations

from datetime import date

import pytest

from travel_agent.app.connectors.visa import entry_requirements as visa
from travel_agent.app.llm import flight_search_links, geo_resolver
from travel_agent.app.llm.geo_resolver import ResolvedPlace
from travel_agent.app.schemas.brief import TripBrief


@pytest.fixture(autouse=True)
def _clear_geo_cache() -> None:
    geo_resolver.clear_cache()


def test_resolve_place_returns_none_when_llm_disabled() -> None:
    # conftest의 autouse 픽스처가 ENABLE_LIVE_LLM=false로 강제 → 카탈로그 폴백만 사용.
    assert geo_resolver.resolve_place("시즈오카") is None


def test_resolve_place_caches_single_llm_call(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_llm(name: str) -> ResolvedPlace:
        calls["n"] += 1
        return ResolvedPlace(country_ko="일본", iata="FSZ", skyscanner="fsz", hub_note=None)

    monkeypatch.setattr(geo_resolver, "_llm_resolve", fake_llm)
    first = geo_resolver.resolve_place("시즈오카")
    second = geo_resolver.resolve_place("시즈오카, 일본")  # 정규화하면 같은 키
    assert first == second
    assert calls["n"] == 1  # 두 번째는 캐시 적중


def test_flight_links_resolve_unlisted_city_via_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    hub = "직항이 적어 나고야(NGO) 경유 추천"

    def fake_resolve(name: str) -> ResolvedPlace | None:
        if "시즈오카" in name:
            return ResolvedPlace(country_ko="일본", iata="NGO", skyscanner="ngo", hub_note=hub)
        return None  # 서울은 카탈로그(ICN)에서 잡힘

    monkeypatch.setattr(geo_resolver, "resolve_place", fake_resolve)
    brief = TripBrief(
        currency="KRW",
        origin="서울",
        destinations=["시즈오카"],
        selected_destination="시즈오카",
        start_date=date(2026, 7, 3),
        end_date=date(2026, 7, 7),
        travelers=1,
    )
    links = flight_search_links.build_flight_search_links(brief)
    assert links is not None
    assert "ICN-NGO" in links.naver_url
    assert "/sel/ngo/" in links.skyscanner_url
    assert links.note == hub  # 인근 허브 안내가 결과에 함께 실린다


def test_resolve_country_identifies_unlisted_city_via_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        geo_resolver,
        "resolve_place",
        lambda name: ResolvedPlace(country_ko="일본", iata="FSZ", skyscanner="fsz", hub_note=None),
    )
    assert visa.resolve_country("시즈오카") == "일본"

    # 비자 규칙까지 일본 데이터로 채워진다(무비자 90일).
    result = visa.lookup_entry_requirements("시즈오카", "대한민국")
    assert result.destination_country == "일본"
    assert result.visa_free_days == 90
    assert result.requires_official_verification is True


def test_resolve_country_normalizes_schengen_country(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # LLM이 '프랑스'를 주면 데이터셋 키 '유럽(셰겐)'으로 정규화되어야 한다.
    france = ResolvedPlace(country_ko="프랑스", iata="NCE", skyscanner="nce", hub_note=None)
    monkeypatch.setattr(geo_resolver, "resolve_place", lambda name: france)
    assert visa.resolve_country("니스") == "유럽(셰겐)"


def test_resolve_country_keeps_catalog_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    # 카탈로그에 있는 도시는 LLM을 호출하지 않는다.
    def boom(name: str) -> ResolvedPlace:
        raise AssertionError("카탈로그에 있으면 LLM을 부르면 안 됨")

    monkeypatch.setattr(geo_resolver, "resolve_place", boom)
    assert visa.resolve_country("도쿄") == "일본"
    assert visa.resolve_country("Osaka, Japan") == "일본"
