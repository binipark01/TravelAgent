from __future__ import annotations

from travel_agent.app.agents.supervisor import TravelSupervisorAgent
from travel_agent.app.schemas.brief import TripBrief
from travel_agent.app.schemas.trip import TripPlanState


def _switch_only() -> TravelSupervisorAgent:
    # _apply_destination_switch는 staticmethod 헬퍼(_same_city·_reset_*)만 쓰므로,
    # 무거운 __init__(프로바이더·LLM) 없이 인스턴스를 만들어 순수 로직만 검증한다.
    return TravelSupervisorAgent.__new__(TravelSupervisorAgent)


def test_switching_city_clears_old_city_inputs_and_results() -> None:
    # 히로시마 계획 상태에서 다음 발화가 '파리'로 바뀐 상황을 만든다.
    state = TripPlanState(
        trip_id="trip_switch",
        raw_user_message="파리로 바꿔서 일정 짜줘",
        currency="KRW",
        selected_destination="히로시마",
        brief=TripBrief(
            destinations=["파리"],  # intake가 최신 발화의 목적지로 교체
            selected_destination="히로시마",
            must_include=["미야지마", "히로시마 시내"],  # 이전 도시 편집이 남아 있음
            must_avoid=["원폭돔 혼잡 시간"],
            clarification="히로시마·미야지마 동선을 더 정확히 짤 수 있어요.",
        ),
    )
    state.constraints["flight_sig"] = "old"

    _switch_only()._apply_destination_switch(state)

    # 목적지는 재선택되도록 비워지고, 이전 도시 편집·안내 입력은 모두 사라진다.
    assert state.selected_destination is None
    assert state.brief.selected_destination is None
    assert state.brief.must_include == []
    assert state.brief.must_avoid == []
    assert state.brief.clarification is None
    # 재검색 서명 캐시도 비워져 새 도시로 다시 검색한다.
    assert "flight_sig" not in state.constraints


def test_same_city_follow_up_keeps_inputs() -> None:
    # 같은 도시(보완·편집 턴)면 전환이 아니므로 must_include 등을 보존한다.
    state = TripPlanState(
        trip_id="trip_same",
        raw_user_message="둘째 날 한적한 곳 넣어줘",
        currency="KRW",
        selected_destination="파리",
        brief=TripBrief(
            destinations=["파리"],
            selected_destination="파리",
            must_include=["에펠탑"],
        ),
    )

    _switch_only()._apply_destination_switch(state)

    assert state.selected_destination == "파리"
    assert state.brief.must_include == ["에펠탑"]
