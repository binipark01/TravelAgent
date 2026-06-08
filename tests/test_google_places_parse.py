from __future__ import annotations

from travel_agent.app.connectors.places.google_places_browser import (
    build_maps_query,
    place_to_poi_option,
)


def test_place_to_poi_option_maps_fields() -> None:
    poi = place_to_poi_option(
        {
            "name": "GYUMON Sapporo",
            "rating": 4.9,
            "reviews": 1200,
            "category": "스키야키 전문점",
            "source_url": "https://www.google.com/maps",
        },
        "Sapporo",
        "KRW",
    )

    assert poi.title == "GYUMON Sapporo"
    assert poi.rating == 4.9
    assert poi.type == "스키야키 전문점"
    assert poi.metadata.source_ref.provider == "google_maps"
    assert poi.metadata.is_mock is False
    assert any("평점 4.9" in note for note in poi.notes)


def test_place_to_poi_option_without_rating() -> None:
    poi = place_to_poi_option({"name": "이름만", "source_url": "u"}, "Osaka", "KRW")

    assert poi.rating is None
    assert poi.type == "맛집"


def test_build_maps_query_strips_country() -> None:
    assert build_maps_query("Sapporo, Japan") == "best restaurants in Sapporo"
    assert build_maps_query("방콕") == "best restaurants in 방콕"
