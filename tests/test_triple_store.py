from __future__ import annotations

import json
from datetime import date

import pytest

from travel_agent.app.agents.route_optimizer import RouteAgent
from travel_agent.app.connectors.course_store import triple_store
from travel_agent.app.providers.base import build_mock_provider_bundle
from travel_agent.app.schemas.brief import TripBrief
from travel_agent.app.schemas.trip import TripPlanState
from travel_agent.app.utils.ids import new_id

# 작은 fixture 도시 파일(도쿄): POI 좌표·평점 + 한 코스 키.
_FIXTURE = {
    "pois": {
        "나리타국제공항": [35.770178, 140.384321, 4.2, "관광명소", "attraction", "나리타 국제공항"],
        "센소지": [35.714765, 139.796655, 4.3, "관광명소", "attraction", "센소지"],
        "이치란라멘": [35.7117, 139.798, 4.5, "음식점", "restaurant", "이치란 라멘"],
        "도쿄타워": [35.65858, 139.745433, 4.4, "관광명소", "attraction", "도쿄 타워"],
    },
    "courses": {
        "2박 3일|혼자|관광보다 먹방|빼곡한 일정 선호": [
            ["나리타 국제공항", "센소지", "이치란 라멘"],
            ["도쿄 타워"],
            ["나리타 국제공항"],
        ],
    },
}


@pytest.fixture()
def store_dir(tmp_path, monkeypatch):
    d = tmp_path / "triple-store"
    d.mkdir()
    (d / "도쿄.json").write_text(json.dumps(_FIXTURE, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("TRIPLE_STORE_DIR", str(d))
    triple_store.clear_cache()
    yield d
    triple_store.clear_cache()


def test_has_city(store_dir) -> None:
    assert triple_store.has_city("도쿄") is True
    assert triple_store.has_city("제주") is False


def test_lookup_poi_exact_and_fuzzy(store_dir) -> None:
    info = triple_store.lookup_poi("도쿄", "센소지·나카미세도리(浅草寺)")  # 부분일치
    assert info is not None
    assert info.lat == 35.714765 and info.lng == 139.796655
    assert info.rating == 4.3 and info.type == "attraction"
    assert triple_store.lookup_poi("도쿄", "없는장소") is None
    assert triple_store.lookup_poi("제주", "센소지") is None  # 스토어 없는 도시


def test_style_and_fatigue_mapping() -> None:
    assert triple_store.style_for_interests(["맛집", "먹방"]) == "관광보다 먹방"
    assert triple_store.style_for_interests(["온천", "힐링"]) == "여유롭게 힐링"
    assert triple_store.style_for_interests([]) == "유명 관광지는 필수"
    assert triple_store.fatigue_for_pace("여유롭게") == "널널한 일정 선호"
    assert triple_store.fatigue_for_pace("빡세게") == "빼곡한 일정 선호"


def test_lookup_course_builds_days_with_coords(store_dir) -> None:
    course = triple_store.lookup_course("도쿄", 3, interests=["맛집"], who="혼자", pace="빼곡")
    assert course is not None
    assert len(course.days) == 3
    first = course.days[0][0]
    assert first.name == "나리타 국제공항" and first.lat == 35.770178
    # 식당 타입이 인식된다.
    assert any(s.type == "restaurant" for s in course.days[0])
    # 일수 7일은 범위 밖 → None.
    assert triple_store.lookup_course("도쿄", 7) is None


def test_route_agent_uses_store_course_with_coords(store_dir) -> None:
    st = TripPlanState(trip_id=new_id("t"), currency="KRW", raw_user_message="도쿄 3일")
    st.brief = TripBrief(
        selected_destination="도쿄", destinations=["도쿄"],
        start_date=date(2026, 7, 10), end_date=date(2026, 7, 12),
        duration_days=3, must_include=["맛집"],
    )
    st.selected_destination = "도쿄"
    RouteAgent(build_mock_provider_bundle().routes).run(st)
    it = st.optimized_itinerary
    assert it and len(it.days) == 3
    # 스토어 코스에서 왔으므로 관광 항목에 실좌표가 박힌다(지도 정확도).
    sights = [x for d in it.days for x in d.items if x.type == "관광지"]
    assert sights and all(x.location.latitude is not None for x in sights)
    # 공항 북엔드 유지.
    assert "공항" in it.days[0].items[0].title


def test_store_travel_caps_airport_legs() -> None:
    from travel_agent.app.connectors.course_store.triple_store import CourseStop

    agent = RouteAgent(build_mock_provider_bundle().routes)
    airport = CourseStop("나리타 국제공항", "attraction", 35.77, 140.38, 4.2, "관광명소")
    city = CourseStop("아사쿠사", "attraction", 35.72, 139.80, 4.4, "관광명소")
    near = CourseStop("센소지", "attraction", 35.715, 139.797, 4.3, "관광명소")
    # 공항이 끼면 직선거리 과대추정 대신 고정 75분.
    assert agent._store_travel(airport, city) == 75
    assert agent._store_travel(city, airport) == 75
    # 가까운 시내끼리는 좌표 기반(75분 미만), 마지막 stop은 0.
    assert 0 < agent._store_travel(city, near) < 75
    assert agent._store_travel(city, None) == 0
