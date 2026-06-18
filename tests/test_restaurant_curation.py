from __future__ import annotations

from travel_agent.app.connectors.places.google_places_browser import (
    _curate_diverse_restaurants,
)


def test_restaurant_curation_diversifies_cuisine() -> None:
    # 평점만 보면 스시집(높은 평점)만 뽑힌다 → 종류를 섞어야 한다.
    places = [
        {"name": "스시A", "rating": 4.9, "reviews": 30, "category": "스시 음식점"},
        {"name": "스시B", "rating": 4.8, "reviews": 50, "category": "초밥집"},
        {"name": "스시C", "rating": 4.8, "reviews": 40, "category": "스시"},
        {"name": "스시D", "rating": 4.7, "reviews": 35, "category": "회전초밥"},
        {"name": "라멘A", "rating": 4.6, "reviews": 1200, "category": "라멘 전문점"},
        {"name": "이자카야A", "rating": 4.5, "reviews": 800, "category": "이자카야"},
        {"name": "야키니쿠A", "rating": 4.4, "reviews": 300, "category": "야키니쿠"},
        {"name": "카페A", "rating": 4.7, "reviews": 200, "category": "카페"},
    ]
    picked = _curate_diverse_restaurants(places, 6)
    names = [p["name"] for p in picked]
    cats = [p["category"] for p in picked]

    assert len(picked) == 6
    sushi = sum(("스시" in c) or ("초밥" in c) for c in cats)
    assert sushi <= 2, f"스시만 몰림: {names}"
    # 다른 종류(라멘/이자카야/야키니쿠/카페)가 최소 3종류는 들어가야 다양하다.
    assert {"라멘A", "이자카야A", "야키니쿠A", "카페A"} & set(names)


def test_restaurant_curation_review_weighted() -> None:
    # 리뷰 적은 4.9는 평균 쪽으로 보정되어, 리뷰 많은 4.6보다 아래로 내려간다.
    places = [
        {"name": "스시희소", "rating": 4.9, "reviews": 3, "category": "스시"},
        {"name": "라멘대중", "rating": 4.6, "reviews": 5000, "category": "라멘"},
        {"name": "기타1", "rating": 4.1, "reviews": 500, "category": "이자카야"},
        {"name": "기타2", "rating": 4.2, "reviews": 600, "category": "카페"},
    ]
    picked = _curate_diverse_restaurants(places, 4)
    assert picked[0]["name"] == "라멘대중"
    assert picked.index(places[1]) < picked.index(places[0])  # 라멘대중이 스시희소보다 앞
