from __future__ import annotations

from travel_agent.app.connectors.safety.advisories import lookup_safety_info


def test_japan_safety_has_emergency_numbers() -> None:
    info = lookup_safety_info("Sapporo")
    assert info is not None
    assert info.destination_country == "일본"
    numbers = {c.number for c in info.emergency_contacts}
    assert "110" in numbers  # 경찰
    assert "119" in numbers  # 구급·소방
    assert "3210-0404" in info.consular_call_center
    assert info.insurance_tips
    assert info.local_cautions
    assert info.metadata.is_mock is False


def test_thailand_has_tourist_police() -> None:
    info = lookup_safety_info("방콕")
    assert info is not None
    labels = {c.label for c in info.emergency_contacts}
    assert any("관광경찰" in label for label in labels)


def test_philippines_has_explicit_advisory() -> None:
    info = lookup_safety_info("Cebu")
    assert info is not None
    assert info.travel_advisory is not None
    assert "여행경보" in info.travel_advisory


def test_unknown_destination_returns_none() -> None:
    assert lookup_safety_info("Reykjavik") is None
