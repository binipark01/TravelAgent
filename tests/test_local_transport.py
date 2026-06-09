from __future__ import annotations

from travel_agent.app.connectors.routes.local_transport import (
    lookup_local_transport,
    resolve_city,
)


def test_resolve_city_handles_aliases() -> None:
    assert resolve_city("Sapporo") == "삿포로"
    assert resolve_city("삿포로") == "삿포로"
    assert resolve_city("Tokyo, Japan") == "도쿄"
    assert resolve_city("다낭") == "다낭"
    assert resolve_city("Nowhere City") is None


def test_lookup_returns_transfers_and_passes() -> None:
    plan = lookup_local_transport("삿포로")
    assert plan is not None
    assert plan.city == "삿포로"
    assert len(plan.airport_transfers) >= 1
    assert len(plan.transit_passes) >= 1
    assert all(item.category == "airport" for item in plan.airport_transfers)
    assert all(item.category == "pass" for item in plan.transit_passes)
    assert plan.source_url
    assert plan.metadata.is_mock is False


def test_lookup_unknown_city_is_none() -> None:
    assert lookup_local_transport("Reykjavik") is None


def test_okinawa_recommends_rental_car() -> None:
    plan = lookup_local_transport("오키나와")
    assert plan is not None
    names = [item.name for item in plan.airport_transfers]
    assert any("렌터카" in name for name in names)
