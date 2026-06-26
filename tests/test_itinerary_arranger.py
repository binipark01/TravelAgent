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


def test_community_course_disabled_returns_none() -> None:
    # conftest: ENABLE_LIVE_LLM=false → 웹검색 비활성 → None(RouteAgent가 배치기로 폴백).
    from travel_agent.app.llm.itinerary_arranger import curate_community_course

    assert (
        curate_community_course(
            "오사카", days_count=3, interests=["맛집"], start_date=date(2026, 7, 3)
        )
        is None
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


# --- A1: _parse_days 직접 호출로 형식 일탈 방어 검증 ---


def test_parse_days_skips_malformed_entries() -> None:
    raw_days = [
        "문자열날",  # dict 아님 → 무시
        {"day": 1, "area": "A", "stops": "이건리스트가아님"},  # stops 비-리스트 → 무시
        {"day": 2, "area": "B", "stops": []},  # stops 비어 있음 → 무시(stop 없는 날 제외)
        {
            "day": 3,
            "area": "C",
            "note": "  ",  # 공백 note → None
            "stops": [
                {"duration_min": 60},  # title 없음 → 이 stop 제외
                {"title": "  ", "duration_min": 60},  # 빈 title → 제외
                {"title": "유효장소", "duration_min": 90, "travel_to_next_min": 10},
            ],
            "lunch": "",  # 빈 lunch → None
            "dinner": "식당",
        },
    ]
    result = itinerary_arranger._parse_days(raw_days, days_count=5)
    assert result is not None
    # stop이 하나도 없는 날은 빠지고, 유효 stop이 있는 day 3만 남는다.
    assert len(result.days) == 1
    day = result.days[0]
    assert day.area == "C"
    assert day.note is None  # 공백 → None
    assert day.lunch is None  # 빈 문자열 → None
    assert day.dinner == "식당"
    assert [s.title for s in day.stops] == ["유효장소"]  # title 없는/빈 stop 제외


def test_parse_days_returns_none_for_empty_or_nonlist() -> None:
    assert itinerary_arranger._parse_days("not-a-list", days_count=3) is None
    assert itinerary_arranger._parse_days([], days_count=3) is None
    # 모든 날이 무효(stop 없음)면 None.
    assert itinerary_arranger._parse_days([{"day": 1, "stops": []}], days_count=3) is None


# --- 22시 결정적 캡: 비-야경 관광은 22시 전에 잘리고, 야경·anchor·식사는 보존 ---


def _late_arrangement() -> ArrangedDay:
    # 길게 늘어져 22시를 넘기는 비-야경 stop들 + 야경 + 숙소 복귀(anchor).
    return ArrangedDay(
        day=3,
        area="사도섬",
        note="섬 당일치기",
        stops=[
            ArrangedStop("사도금산", 240, 60, "버스"),  # 10:00~14:00
            ArrangedStop("도키노모리 공원", 240, 60, "버스"),  # 15:00~19:00
            ArrangedStop("슈쿠네기 마을", 180, 60, "버스"),  # 20:00~23:00 → 캡, 제외
            ArrangedStop("료쓰항 야경 전망대", 60, 30, "도보"),  # 야경 → 유지
            ArrangedStop("숙소 부근(니가타역)", 30, 0, "제트포일"),  # anchor → 유지
        ],
        lunch=None,
        dinner=None,
    )


def test_non_night_sightseeing_capped_at_22() -> None:
    from datetime import time as time_cls

    agent = RouteAgent(build_mock_provider_bundle().routes)
    day = agent._build_arranged_day(3, None, _late_arrangement(), {}, {}, _state())
    titles = [item.title for item in day.items]
    # 22시를 넘기는 비-야경 관광은 제외된다.
    assert "슈쿠네기 마을" not in titles
    # 야경 명소는 22시 넘겨도 유지된다.
    assert any("야경" in t for t in titles)
    # 숙소 복귀(anchor)는 유지된다 — 그날이 제대로 닫힌다.
    assert any("숙소" in t for t in titles)
    # 캡 이전 정상 관광은 그대로.
    assert "사도금산" in titles and "도키노모리 공원" in titles
    # 비-야경 관광 항목들은 22시 안에 끝난다.
    sightseeing = [it for it in day.items if it.type == "관광지"]
    assert all(it.end_time <= time_cls(22, 0) for it in sightseeing)


def test_cap_preserves_meals() -> None:
    from datetime import time as time_cls

    # 점심·저녁이 있는 늦은 일정에서도 식사는 보존된다(캡은 관광에만 적용).
    arranged = ArrangedDay(
        day=2,
        area="중심",
        note=None,
        stops=[
            ArrangedStop("A", 240, 30, "도보"),  # 10:00~14:00
            ArrangedStop("B", 240, 30, "도보"),  # 늦게
            ArrangedStop("C", 180, 0, "도보"),  # 22시 초과 → 캡
        ],
        lunch="점심집",
        dinner="저녁집",
    )
    agent = RouteAgent(build_mock_provider_bundle().routes)
    day = agent._build_arranged_day(2, None, arranged, {}, {}, _state())
    meal_types = {m.meal_type for m in day.meals}
    assert "lunch" in meal_types and "dinner" in meal_types
    # 저녁 시작은 22시 캡 창 안(식사 start는 18~22시).
    dinner = next(m for m in day.meals if m.meal_type == "dinner")
    assert dinner.start_time <= time_cls(22, 0)


def test_normal_day_not_affected_by_cap() -> None:
    from datetime import time as time_cls

    # 일찍 끝나는 평범한 날은 캡이 아무것도 떨구지 않는다.
    arranged = ArrangedDay(
        day=1, area="중심", note=None,
        stops=[
            ArrangedStop("A", 90, 15, "도보"),
            ArrangedStop("B", 90, 15, "도보"),
            ArrangedStop("C", 90, 0, "도보"),
        ],
        lunch=None, dinner=None,
    )
    agent = RouteAgent(build_mock_provider_bundle().routes)
    day = agent._build_arranged_day(1, None, arranged, {}, {}, _state())
    assert [it.title for it in day.items] == ["A", "B", "C"]  # 모두 유지
    assert all(it.end_time <= time_cls(22, 0) for it in day.items)


def test_cap_catches_past_midnight_wrap() -> None:
    from datetime import time as time_cls

    # 사도섬 실제 버그 재현: 자정을 넘겨 wrap되는(예: 01:05) 비-야경 stop도 잘려야 한다.
    # _add_minutes가 25:05→01:05로 wrap하므로 시각만 보면 22시보다 작아 보이는 함정.
    arranged = ArrangedDay(
        day=3, area="사도섬", note="섬",
        stops=[
            ArrangedStop("사도금산", 300, 120, "버스"),  # 10:00~15:00
            ArrangedStop("슈쿠네기 마을", 300, 120, "버스"),  # 17:00~22:00 경계
            ArrangedStop("료쓰항", 180, 60, "제트포일"),  # 자정 넘김 → 잘림
            ArrangedStop("숙소 부근(니가타역)", 30, 0, "도보"),  # anchor 유지
        ],
        lunch=None, dinner=None,
    )
    agent = RouteAgent(build_mock_provider_bundle().routes)
    day = agent._build_arranged_day(3, None, arranged, {}, {}, _state())
    # 자정을 넘기는 관광은 일정에 남지 않는다.
    sightseeing = [it for it in day.items if it.type == "관광지"]
    for it in sightseeing:
        # 22시 이전이고 자정 wrap(00:00~09:59)도 아님.
        assert it.end_time <= time_cls(22, 0)
        assert it.end_time >= time_cls(10, 0)
    assert any("숙소" in it.title for it in day.items)  # anchor 복귀는 유지


def test_past_day_cap_helper_handles_wrap() -> None:
    from datetime import time as time_cls

    assert RouteAgent._past_day_cap(time_cls(22, 30)) is True  # 22시 직후
    assert RouteAgent._past_day_cap(time_cls(1, 5)) is True  # 자정 넘겨 wrap(01:05)
    assert RouteAgent._past_day_cap(time_cls(9, 0)) is True  # 10시 이전 = wrap
    assert RouteAgent._past_day_cap(time_cls(21, 59)) is False  # 22시 직전 OK
    assert RouteAgent._past_day_cap(time_cls(18, 0)) is False


def test_night_view_detection() -> None:
    agent = RouteAgent(build_mock_provider_bundle().routes)
    assert agent._is_night_view(ArrangedStop("도쿄타워 전망대", 60, 0, "도보"), None)
    assert agent._is_night_view(ArrangedStop("우메다 스카이빌딩 야경", 60, 0, "도보"), None)
    assert not agent._is_night_view(ArrangedStop("기요미즈데라", 90, 0, "도보"), None)
    # anchor 판정.
    assert agent._is_anchor_stop(ArrangedStop("간사이공항(출국)", 30, 0, "전철"), None)
    assert agent._is_anchor_stop(ArrangedStop("숙소 부근(난바역)", 30, 0, "도보"), None)
    assert not agent._is_anchor_stop(ArrangedStop("도톤보리", 60, 0, "도보"), None)
