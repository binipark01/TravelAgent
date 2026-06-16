from __future__ import annotations

from datetime import date

from travel_agent.app.agents.supervisor import TravelSupervisorAgent
from travel_agent.app.schemas.brief import TripBrief
from travel_agent.app.schemas.trip import TripPlanState


def _state() -> TripPlanState:
    return TripPlanState(
        trip_id="t",
        raw_user_message="x",
        selected_destination="Sapporo",
        brief=TripBrief(
            origin="서울",
            destinations=["Sapporo"],
            start_date=date(2026, 7, 3),
            end_date=date(2026, 7, 7),
            travelers=2,
            currency="KRW",
        ),
    )


def test_needs_search_reuses_when_inputs_unchanged() -> None:
    # __init__(무거운 RunContext)을 건너뛰고 순수 로직만 검증한다.
    sup = object.__new__(TravelSupervisorAgent)
    state = _state()

    # 결과가 아직 없으면 검색이 필요하다.
    assert sup._needs_search(state, "flight", have_results=False) is True
    # 결과가 있고 검색 입력이 그대로면 재사용(스킵).
    assert sup._needs_search(state, "flight", have_results=True) is False

    # 날짜가 바뀌면 다시 검색한다.
    state.brief.start_date = date(2026, 8, 1)
    assert sup._needs_search(state, "flight", have_results=True) is True


def test_edit_signals_do_not_trigger_research() -> None:
    sup = object.__new__(TravelSupervisorAgent)
    state = _state()
    sup._needs_search(state, "flight", have_results=False)  # 서명 저장
    sup._needs_search(state, "accommodation", have_results=False)

    # 편집 신호(must_avoid)는 검색 서명에 들어가지 않아 항공/숙소는 재사용된다.
    state.brief.must_avoid = ["공원"]
    assert sup._needs_search(state, "flight", have_results=True) is False
    assert sup._needs_search(state, "accommodation", have_results=True) is False

    # 반면 맛집 위주(must_include)는 POI 검색 결과를 바꾸므로 재검색된다.
    sup._needs_search(state, "restaurant", have_results=False)
    state.brief.must_include = ["food"]
    assert sup._needs_search(state, "restaurant", have_results=True) is True


def test_has_prior_results_detects_continuation() -> None:
    sup = object.__new__(TravelSupervisorAgent)
    state = _state()
    assert sup._has_prior_results(state) is False
    state.poi_candidates = ["dummy"]  # 결과 존재 → 이어가기 턴
    assert sup._has_prior_results(state) is True


def test_focused_plan_scopes_single_domain() -> None:
    from travel_agent.app.agents.core_planner import CorePlannerAgent
    from travel_agent.app.schemas.brief import TripBrief

    planner = CorePlannerAgent(enabled=False)

    def plan_for(msg, pref=None):
        brief = TripBrief(currency="KRW", transport_preference=pref)
        state = TripPlanState(trip_id="t", raw_user_message=msg, brief=brief)
        return planner.plan(state).agents

    # 단일 도메인은 좁게
    assert plan_for("삿포로 항공권 찾아줘", pref="flight, flight_search") == ["flight"]
    assert plan_for("삿포로 4성급 이상 호텔 추천해줘") == ["accommodation"]
    # 종합 요청은 넓게(일정/맛집위주 등)
    assert "route" in plan_for("삿포로 3박4일 여행 일정 짜줘")
    full = plan_for("일본 4박5일 가고싶어 맛집이랑 쇼핑 위주")
    assert "accommodation" in full and "route" in full  # 맛집만으로 좁혀지지 않음
