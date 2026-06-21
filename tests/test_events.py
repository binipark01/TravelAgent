from __future__ import annotations

from datetime import date

import pytest

from travel_agent.app.agents.events import LocalEventsAgent
from travel_agent.app.llm import curator
from travel_agent.app.schemas.brief import TripBrief
from travel_agent.app.schemas.trip import TripPlanState


def _state() -> TripPlanState:
    return TripPlanState(
        trip_id="trip_ev",
        raw_user_message="교토 여행",
        currency="KRW",
        selected_destination="교토",
        brief=TripBrief(
            destinations=["교토"],
            start_date=date(2026, 7, 18),
            end_date=date(2026, 7, 21),
        ),
    )


def test_curate_events_disabled_returns_none() -> None:
    # conftest: ENABLE_LIVE_LLM=false → 웹검색 비활성 → None(행사 지어내지 않음).
    assert curator.curate_events("교토", date(2026, 7, 18), date(2026, 7, 21)) is None


def test_events_agent_noop_when_disabled() -> None:
    state = _state()
    LocalEventsAgent().run(state)
    assert state.local_events is None


def test_curate_events_parses_and_drops_sourceless(monkeypatch: pytest.MonkeyPatch) -> None:
    curator.clear_cache()
    monkeypatch.setattr(curator, "_enabled", lambda settings: True)
    monkeypatch.setattr(
        curator,
        "_run",
        lambda prompt, settings: {
            "destination": "교토",
            "summary": "여름 축제 시즌",
            "events": [
                {
                    "name": "기온 마쓰리",
                    "category": "축제",
                    "period": "7/17~24",
                    "venue": "야사카 신사 일대",
                    "highlight": "교토 3대 축제",
                    "source_url": "https://example.com/gion",
                },
                # 출처 없는 행사 → 신뢰 불가, 제외되어야 한다(지어내기 방지).
                {"name": "출처없는행사", "category": "전시", "period": "7/20"},
            ],
        },
    )
    guide = curator.curate_events("교토", date(2026, 7, 18), date(2026, 7, 21))
    curator.clear_cache()

    assert guide is not None
    names = [event.name for event in guide.events]
    assert "기온 마쓰리" in names
    assert "출처없는행사" not in names
    assert guide.date_range == "2026-07-18 ~ 2026-07-21"
    assert guide.events[0].venue == "야사카 신사 일대"


def test_curate_events_returns_none_when_no_valid_events(monkeypatch: pytest.MonkeyPatch) -> None:
    curator.clear_cache()
    monkeypatch.setattr(curator, "_enabled", lambda settings: True)
    # 그 기간에 행사가 없으면 빈 배열 → None(카드 미표시).
    monkeypatch.setattr(curator, "_run", lambda prompt, settings: {"summary": "없음", "events": []})
    assert curator.curate_events("교토", date(2026, 7, 18), date(2026, 7, 21)) is None
    curator.clear_cache()
