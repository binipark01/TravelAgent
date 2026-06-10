from __future__ import annotations

from travel_agent.app.connectors.nearby.day_trips import lookup_nearby


def test_sapporo_nearby_includes_otaru() -> None:
    guide = lookup_nearby("Sapporo")
    assert guide is not None
    assert guide.hub == "삿포로"
    names = [d.name for d in guide.destinations]
    assert "오타루" in names
    otaru = next(d for d in guide.destinations if d.name == "오타루")
    assert otaru.travel_time
    assert otaru.transport
    assert otaru.highlights
    assert guide.source_url
    assert guide.metadata.is_mock is False


def test_nearby_resolves_korean_and_alias() -> None:
    assert lookup_nearby("삿포로") is not None
    assert lookup_nearby("Tokyo, Japan") is not None
    assert lookup_nearby("다낭") is not None


def test_each_nearby_destination_has_core_fields() -> None:
    guide = lookup_nearby("오사카")
    assert guide is not None
    assert len(guide.destinations) >= 3
    for dest in guide.destinations:
        assert dest.name and dest.travel_time and dest.transport
        assert dest.source_url


def test_unknown_destination_returns_none() -> None:
    assert lookup_nearby("Reykjavik") is None
