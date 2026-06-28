from __future__ import annotations

import pytest

from travel_agent.app.agents import destination as destination_mod
from travel_agent.app.agents.destination import DestinationDiscoveryAgent
from travel_agent.app.schemas.brief import TripBrief
from travel_agent.app.schemas.trip import TripPlanState
from travel_agent.app.utils.ids import new_id


def _state(brief: TripBrief) -> TripPlanState:
    st = TripPlanState(trip_id=new_id("trip"), currency="KRW", raw_user_message="x")
    st.brief = brief
    return st


def test_explicit_city_is_kept() -> None:
    st = _state(TripBrief(destinations=["도쿄"]))
    DestinationDiscoveryAgent().run(st)
    assert st.selected_destination == "도쿄"
    assert st.destination_candidates == ["도쿄"]


def test_vague_country_without_llm_falls_back_to_default_city() -> None:
    # LLM off(테스트 기본) → 국가명을 거점으로 두지 않고 최후 기본 도시(오사카)로.
    st = _state(TripBrief(destinations=["일본"], destination_hint="일본"))
    DestinationDiscoveryAgent().run(st)
    assert st.selected_destination == "오사카"


def test_vague_hint_uses_llm_recommendation(monkeypatch: pytest.MonkeyPatch) -> None:
    # 분위기·테마 의도(hint)는 LLM 추천 도시로 거점을 정하고 brief.destinations에도 반영한다.
    monkeypatch.setattr(
        destination_mod, "recommend_destinations",
        lambda hint, interests: ["유후", "벳푸", "하코네"],
    )
    brief = TripBrief(destinations=[], destination_hint="일본 온천 힐링")
    st = _state(brief)
    DestinationDiscoveryAgent().run(st)
    assert st.selected_destination == "유후"
    assert st.destination_candidates == ["유후", "벳푸", "하코네"]
    assert brief.destinations == ["유후", "벳푸", "하코네"]  # 하위 에이전트가 쓰게 반영


def test_already_selected_destination_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    # 이미 거점이 정해졌으면 LLM 추천을 부르지 않는다.
    called = {"n": 0}

    def fake_rec(hint, interests):  # noqa: ANN001
        called["n"] += 1
        return ["다낭"]

    monkeypatch.setattr(destination_mod, "recommend_destinations", fake_rec)
    st = _state(TripBrief(destinations=[], destination_hint="따뜻한 데"))
    st.selected_destination = "방콕"
    DestinationDiscoveryAgent().run(st)
    assert st.selected_destination == "방콕"
    assert called["n"] == 0
