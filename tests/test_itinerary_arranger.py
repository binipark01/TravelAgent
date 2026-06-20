from __future__ import annotations

from datetime import date

import pytest

from travel_agent.app.agents import route_optimizer
from travel_agent.app.agents.route_optimizer import RouteAgent
from travel_agent.app.llm import itinerary_arranger
from travel_agent.app.llm.itinerary_arranger import (
    ArrangedDay,
    ArrangedItinerary,
    ArrangedStop,
    arrange_itinerary,
)
from travel_agent.app.providers.base import build_mock_provider_bundle
from travel_agent.app.schemas.brief import TripBrief
from travel_agent.app.schemas.common import Location, Money, SourceRef
from travel_agent.app.schemas.providers import POIOption, ProviderMetadata
from travel_agent.app.schemas.trip import TripPlanState
from travel_agent.app.utils.ids import new_id
from travel_agent.app.utils.time import utc_now


def _poi(title: str, area: str, *, rating: float = 4.3) -> POIOption:
    now = utc_now()
    meta = ProviderMetadata(
        provider_name="test",
        retrieved_at=now,
        source_ref=SourceRef(
            source_id=new_id("src"), provider="test", title="t", reference="r", retrieved_at=now
        ),
    )
    return POIOption(
        poi_id=new_id("poi"),
        title=title,
        type="관광지",
        location=Location(name="시즈오카"),
        area=area,
        estimated_cost=Money(amount=0, currency="KRW"),
        rating=rating,
        recommended_duration_minutes=90,
        metadata=meta,
        notes=["💡 추천 이유"],
    )


def test_arrange_disabled_returns_none() -> None:
    # conftest의 autouse 픽스처가 ENABLE_LIVE_LLM=false → 배치기 비활성 → None.
    assert (
        arrange_itinerary(
            "시즈오카",
            days_count=3,
            attractions=[_poi("니혼다이라", "니혼다이라")],
            restaurants=[],
            pace=None,
            start_date=None,
        )
        is None
    )


def _state() -> TripPlanState:
    return TripPlanState(
        trip_id="trip_arr",
        raw_user_message="시즈오카 여행",
        currency="KRW",
        selected_destination="시즈오카",
        brief=TripBrief(
            origin="서울",
            destinations=["시즈오카"],
            start_date=date(2026, 7, 3),
            end_date=date(2026, 7, 5),
            duration_days=3,
            travelers=2,
            currency="KRW",
        ),
    )


def test_route_agent_builds_itinerary_from_arrangement(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _state()
    state.activity_options = [
        _poi("니혼다이라 유메테라스", "니혼다이라"),
        _poi("구노잔 도쇼구", "구노잔"),
        _poi("미호노마쓰바라", "미호"),
    ]
    state.poi_candidates = [_poi("さわやか", "함박스테이크", rating=4.4)]

    arrangement = ArrangedItinerary(
        days=[
            ArrangedDay(
                day=1,
                area="시미즈·니혼다이라",
                note="후지산 전망 묶음",
                stops=[
                    ArrangedStop("니혼다이라 유메테라스", 75, 10, "로프웨이"),
                    ArrangedStop("구노잔 도쇼구", 90, 0, "도보"),
                ],
                lunch="さわやか",
                dinner=None,
            )
        ]
    )
    monkeypatch.setattr(route_optimizer, "arrange_itinerary", lambda *a, **k: arrangement)

    RouteAgent(build_mock_provider_bundle().routes).run(state)
    itinerary = state.optimized_itinerary
    assert itinerary is not None
    # 날 수만큼 채워진다(배치 1일 + 빈 2일).
    assert len(itinerary.days) == 3

    day1 = itinerary.days[0]
    assert day1.area == "시미즈·니혼다이라"
    assert [item.title for item in day1.items] == ["니혼다이라 유메테라스", "구노잔 도쇼구"]

    # 관광 사이 이동 세그먼트(배치기 이동시간·수단)가 보존된다.
    attr_transfer = next(t for t in day1.transfers if t.mode == "로프웨이")
    assert attr_transfer.origin == "니혼다이라 유메테라스"
    assert attr_transfer.destination == "구노잔 도쇼구"
    assert attr_transfer.travel_minutes == 10

    # 식당(さわやか)으로 가는 이동도 동선에 들어간다(식사 앞에도 이동 표시).
    assert any(t.destination == "さわやか" for t in day1.transfers)

    # 시간이 이동시간을 반영한다(둘째 항목은 첫째 종료+이동 후 시작).
    assert day1.items[0].start_time.hour == 10
    assert day1.items[1].start_time > day1.items[0].end_time

    # 점심이 그날 동선에 들어간다.
    assert any(meal.title == "さわやか" for meal in day1.meals)


def test_no_free_time_and_meal_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import time as time_cls

    state = _state()
    state.activity_options = [_poi("A", "중심"), _poi("B", "중심"), _poi("C", "중심")]
    state.poi_candidates = [_poi("점심집", "중심"), _poi("저녁집", "중심")]
    arrangement = ArrangedItinerary(
        days=[
            ArrangedDay(
                day=1,
                area="중심",
                note=None,
                stops=[
                    ArrangedStop("A", 90, 10, "도보"),
                    ArrangedStop("B", 90, 10, "도보"),
                    ArrangedStop("C", 90, 0, "도보"),
                ],
                lunch="점심집",
                dinner="저녁집",
            )
        ]
    )
    monkeypatch.setattr(route_optimizer, "arrange_itinerary", lambda *a, **k: arrangement)
    monkeypatch.setattr(route_optimizer, "fetch_trip_weather", lambda *a, **k: {})

    RouteAgent(build_mock_provider_bundle().routes).run(state)
    for day in state.optimized_itinerary.days:
        assert day.free_time == []  # 자유 시간 제거
        for meal in day.meals:
            if meal.meal_type == "lunch":
                assert time_cls(11, 0) <= meal.start_time <= time_cls(14, 0)
            if meal.meal_type == "dinner":
                assert time_cls(17, 0) <= meal.start_time <= time_cls(22, 0)


def test_dinner_adaptive_and_meal_dedup(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import time as time_cls

    state = _state()
    state.activity_options = [_poi("A", "중심"), _poi("점심집", "중심")]
    state.poi_candidates = [_poi("점심집", "중심"), _poi("저녁집", "중심")]
    # '점심집'을 관광 stop에도 넣어 중복 상황을 만든다(식당으로도 씀).
    arrangement = ArrangedItinerary(
        days=[
            ArrangedDay(
                day=1,
                area="중심",
                note=None,
                stops=[ArrangedStop("A", 90, 0, "도보"), ArrangedStop("점심집", 60, 0, "도보")],
                lunch="점심집",
                dinner="저녁집",
            )
        ]
    )
    monkeypatch.setattr(route_optimizer, "arrange_itinerary", lambda *a, **k: arrangement)
    monkeypatch.setattr(route_optimizer, "fetch_trip_weather", lambda *a, **k: {})

    RouteAgent(build_mock_provider_bundle().routes).run(state)
    day = state.optimized_itinerary.days[0]
    # 식당으로 쓴 '점심집'은 관광지 items에 중복으로 들어가지 않는다.
    assert "점심집" not in [item.title for item in day.items]
    # 저녁은 17~21시 안(마지막 일정이 일찍 끝나도 18:30 고정 공백이 아니라 당겨짐).
    dinner = next(m for m in day.meals if m.meal_type == "dinner")
    assert time_cls(17, 0) <= dinner.start_time <= time_cls(21, 0)


def test_route_agent_falls_back_to_heuristic_when_no_arrangement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state()
    state.activity_options = [_poi("A", "동부"), _poi("B", "서부")]
    state.poi_candidates = [_poi("식당", "라멘")]
    monkeypatch.setattr(route_optimizer, "arrange_itinerary", lambda *a, **k: None)

    RouteAgent(build_mock_provider_bundle().routes).run(state)
    itinerary = state.optimized_itinerary
    assert itinerary is not None
    assert len(itinerary.days) == 3
    # 폴백 경로는 이동 세그먼트를 만들지 않는다(고정 시간표).
    assert all(len(day.transfers) == 0 for day in itinerary.days)


def test_route_agent_passes_weather_to_arranger(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import date as date_cls

    state = _state()
    state.activity_options = [_poi("미술관", "중심"), _poi("공원", "강변")]
    state.poi_candidates = [_poi("식당", "중심")]

    # 날씨를 알려진 값으로 고정(1일차 비, 2일차 맑음).
    weather = {
        date_cls(2026, 7, 3): "🌧 비 24°/18°",
        date_cls(2026, 7, 4): "☀️ 맑음 28°/19°",
    }
    monkeypatch.setattr(route_optimizer, "fetch_trip_weather", lambda *a, **k: weather)

    captured: dict = {}

    def fake_arrange(*args, **kwargs):  # noqa: ANN002, ANN003
        captured.update(kwargs)
        return None  # 폴백 경로 사용(배치 결과는 이 테스트의 관심사가 아님)

    monkeypatch.setattr(route_optimizer, "arrange_itinerary", fake_arrange)

    RouteAgent(build_mock_provider_bundle().routes).run(state)
    # 배치기에 '일차 번호 → 날씨'가 전달된다.
    assert captured["weather_by_day"][1].startswith("🌧")
    assert captured["weather_by_day"][2].startswith("☀️")
    # 날씨가 일정 표시에도 붙는다.
    day1 = state.optimized_itinerary.days[0]
    assert day1.weather and day1.weather.startswith("🌧")


def test_arranger_parses_and_caps_llm_output(monkeypatch: pytest.MonkeyPatch) -> None:
    # LLM 활성 + run_codex_json을 가짜로 대체해 파싱·보정 로직만 검증한다.
    monkeypatch.setattr(itinerary_arranger, "_enabled", lambda: True)
    stop_a = {"title": "A", "duration_min": 9999, "travel_to_next_min": -5, "travel_mode": ""}
    stop_b = {"title": "B", "duration_min": 60, "travel_to_next_min": 20, "travel_mode": "버스"}
    fake = {
        "days": [
            {
                "day": 1,
                "area": "중심부",
                "note": "도보 코스",
                "stops": [stop_a, stop_b],
                "lunch": "식당",
                "dinner": None,
            }
        ]
    }
    monkeypatch.setattr(itinerary_arranger, "run_codex_json", lambda *a, **k: fake)

    result = arrange_itinerary(
        "시즈오카",
        days_count=2,
        attractions=[_poi("A", "x"), _poi("B", "y")],
        restaurants=[_poi("식당", "z")],
        pace="relaxed",
        start_date=date(2026, 7, 3),
    )
    assert result is not None
    stops = result.days[0].stops
    assert stops[0].duration_min == 240  # 9999 → 상한 240
    assert stops[0].travel_to_next_min == 0  # 음수 → 0
    assert stops[0].travel_mode == "이동"  # 빈 값 → 기본
    assert stops[1].travel_mode == "버스"
