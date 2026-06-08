from __future__ import annotations

from travel_agent.app.connectors.places.google_places_browser import (
    build_maps_query,
    detect_interest,
    place_to_poi_option,
)


def test_detect_interest_and_query() -> None:
    assert detect_interest("삿포로 스시 맛집 추천해줘", "restaurant") == "sushi"
    assert detect_interest("라멘 먹고싶어", "restaurant") == "ramen"
    assert detect_interest("박물관 위주로 보고싶어", "attraction") == "museums"
    assert detect_interest("온천 가고싶다", "attraction") == "onsen hot springs"
    assert detect_interest("그냥 여행", "restaurant") is None
    # 취향이 있으면 검색어에 반영된다.
    assert build_maps_query("Sapporo", "restaurant", "sushi") == "best sushi in Sapporo"
    assert build_maps_query("Sapporo", "restaurant") == "best restaurants in Sapporo"


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
