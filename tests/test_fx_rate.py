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
