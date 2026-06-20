from __future__ import annotations

from travel_agent.app.llm.curator import curate_multicity
from travel_agent.app.schemas.trip import TripPlanState


class MultiCityAgent:
    """복수 목적지(파리+런던 등)일 때 도시별 일수 배분 + 도시간 이동 오버뷰를 채운다.

    각 도시 항공·숙소를 완전히 쪼개진 않고(단일 목적지로 상세 계획), 멀티시티 동선 안내를
    제공한다. 목적지가 1개거나 LLM이 꺼져 있으면 비워 둔다.
    """

    def run(self, state: TripPlanState) -> TripPlanState:
        brief = state.brief
        if not brief or len(brief.destinations) < 2:
            return state
        plan = curate_multicity(brief.destinations, total_days=brief.duration_days)
        if plan is not None:
            state.multicity_plan = plan
        return state
