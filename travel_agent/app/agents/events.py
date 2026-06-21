from __future__ import annotations

from travel_agent.app.llm.curator import curate_events
from travel_agent.app.schemas.trip import TripPlanState


class LocalEventsAgent:
    """여행 날짜에 목적지에서 열리는 축제·전시·행사를 LLM 웹검색으로 채운다.

    그 기간에 실제로 열리는 행사만 출처와 함께 모은다. 웹검색이 꺼져 있거나, 행사를 못
    찾으면 비워 둔다(없는 행사를 지어내지 않는 '판단' 정보 — 카드도 표시되지 않음).
    """

    def run(self, state: TripPlanState) -> TripPlanState:
        brief = state.brief
        destination = state.selected_destination or (
            brief.destinations[0] if brief and brief.destinations else None
        )
        if not destination:
            return state
        start = brief.start_date if brief else None
        end = brief.end_date if brief else None
        guide = curate_events(destination, start, end)
        if guide is not None and guide.events:
            state.local_events = guide
        return state
