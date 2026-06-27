from __future__ import annotations

from travel_agent.app.connectors.fx import exchange_rate
from travel_agent.app.connectors.fx.exchange_rate import (
    destination_currency,
    fetch_fx_info,
)


def test_destination_currency_maps_country() -> None:
    assert destination_currency("Tokyo") == "JPY"
    assert destination_currency("삿포로") == "JPY"
    assert destination_currency("방콕") == "THB"
    assert destination_currency("다낭") == "VND"
    assert destination_currency("Guam") == "USD"
    assert destination_currency("Nowhere") is None


def test_destination_currency_non_euro_europe() -> None:
    # 셰겐이라도 유로가 아닌 유럽: '유럽(셰겐)'→EUR로 묶이면 틀린다. 도시·국가명으로 먼저 잡는다.
    assert destination_currency("취리히") == "CHF"
    assert destination_currency("Zurich") == "CHF"
    assert destination_currency("스위스") == "CHF"
    assert destination_currency("프라하") == "CZK"
    assert destination_currency("Prague") == "CZK"
    assert destination_currency("부다페스트") == "HUF"
    assert destination_currency("스톡홀름") == "SEK"
    assert destination_currency("오슬로") == "NOK"
    assert destination_currency("코펜하겐") == "DKK"
    # 영국은 셰겐이 아니지만 통화는 GBP(기존 매핑 유지).
    assert destination_currency("런던") == "GBP"


def test_fetch_fx_info_converts_budget(monkeypatch) -> None:
    # 1 KRW = 0.1 JPY (즉 1 JPY = 10 KRW) 라고 가정
    monkeypatch.setattr(exchange_rate, "_fetch_rate", lambda base, target: 0.1)
    info = fetch_fx_info("Sapporo", base_currency="KRW", budget_total_base=1_000_000)
    assert info is not None
    assert info.target_currency == "JPY"
    assert abs(info.base_per_target - 10.0) < 1e-6
    # 100만원 * 0.1 = 10만 엔
    assert round(info.budget_total_target) == 100_000
    assert info.budget_total_target_label is not None
    # 샘플 환산: 10,000엔 = 약 100,000원
    labels = {s.local_label: s.krw_label for s in info.samples}
    assert "10,000엔" in labels
    assert "100,000원" in labels["10,000엔"]
    assert info.tips  # 환전 팁 존재
    assert info.metadata.is_mock is False


def test_fetch_fx_info_returns_none_on_api_failure(monkeypatch) -> None:
    monkeypatch.setattr(exchange_rate, "_fetch_rate", lambda base, target: None)
    assert fetch_fx_info("Tokyo", "KRW", 500_000) is None


def test_fetch_fx_info_none_for_unknown_destination() -> None:
    assert fetch_fx_info("Nowhere", "KRW", 500_000) is None


def test_destination_currency_llm_fallback_for_exotic(monkeypatch) -> None:
    # 정적 맵에 없는 통화(키르기스 KGS 등)는 LLM 리졸버의 ISO 코드로 폴백한다.
    from travel_agent.app.llm.geo_resolver import ResolvedPlace

    monkeypatch.setattr(
        "travel_agent.app.llm.geo_resolver.resolve_place",
        lambda name: ResolvedPlace(
            country_ko="키르기스스탄", iata="FRU", skyscanner="fru", hub_note=None,
            city_en="Bishkek", lat=42.87, lng=74.59, currency="KGS",
        ),
    )
    assert destination_currency("비슈케크") == "KGS"


def test_fetch_fx_info_builds_card_for_exotic_currency(monkeypatch) -> None:
    # 통화 메타가 없는 코드도 generic 메타(코드명·기본 샘플)로 카드를 만든다.
    from travel_agent.app.llm.geo_resolver import ResolvedPlace

    monkeypatch.setattr(
        "travel_agent.app.llm.geo_resolver.resolve_place",
        lambda name: ResolvedPlace(
            country_ko="키르기스스탄", iata="FRU", skyscanner="fru", hub_note=None,
            city_en="Bishkek", lat=42.87, lng=74.59, currency="KGS",
        ),
    )
    monkeypatch.setattr(exchange_rate, "_fetch_rate", lambda base, target: 0.0568)
    info = fetch_fx_info("비슈케크", "KRW", 2_000_000)
    assert info is not None
    assert info.target_currency == "KGS"
    assert info.samples  # generic 메타로 샘플 생성됨
    assert "KGS" in (info.budget_total_target_label or "")
