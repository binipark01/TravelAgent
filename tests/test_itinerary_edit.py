from __future__ import annotations

from types import SimpleNamespace

from travel_agent.app.agents.intake import IntakeAgent
from travel_agent.app.agents.route_optimizer import RouteAgent
from travel_agent.app.schemas.brief import TripBrief


def _pois():
    return [
        SimpleNamespace(title="오타루 운하", type="attraction"),
        SimpleNamespace(title="삿포로 맥주 박물관", type="museum"),
        SimpleNamespace(title="스스키노 시장", type="market"),
    ]


def test_apply_edits_excludes_must_avoid() -> None:
    agent = RouteAgent(None)
    brief = TripBrief(currency="KRW", must_avoid=["박물관"])
    out = agent._apply_edits(_pois(), brief)
    assert all("박물관" not in p.title for p in out)
    assert len(out) == 2


def test_apply_edits_prioritizes_must_include() -> None:
    agent = RouteAgent(None)
    brief = TripBrief(currency="KRW", must_include=["시장"])
    out = agent._apply_edits(_pois(), brief)
    assert out[0].title == "스스키노 시장"


def test_per_day_respects_pace() -> None:
    agent = RouteAgent(None)
    ordered = [0] * 9  # 9곳 / 3일 → 기본 3
    assert agent._per_day(TripBrief(currency="KRW", pace="relaxed"), ordered, 3) == 2
    assert agent._per_day(TripBrief(currency="KRW", pace="packed"), ordered, 3) == 4
    assert agent._per_day(TripBrief(currency="KRW"), ordered, 3) == 3


def test_intake_captures_exclude_intent() -> None:
    agent = IntakeAgent(enable_live_llm=False)
    result = agent.run("삿포로 3박4일 일정인데 박물관은 빼줘")
    assert "박물관" in result.brief.must_avoid

    # 멀티턴: 이전 목적지 유지하면서 제외 의도 누적
    result2 = agent.run("온천도 말고", history=["삿포로 3박4일 일정", "박물관 빼줘"])
    assert "온천" in result2.brief.must_avoid
    assert "박물관" in result2.brief.must_avoid
