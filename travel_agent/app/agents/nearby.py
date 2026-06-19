from __future__ import annotations

from travel_agent.app.connectors.nearby.day_trips import lookup_nearby
from travel_agent.app.llm.curator import curate_nearby
from travel_agent.app.schemas.trip import TripPlanState


class NearbyAgent:
    """목적지 허브 기준 근교 당일치기 명소를 정리해 채운다.

    LLM 웹검색 큐레이션이 켜져 있으면 블로그·관광청을 종합해 추천하고(카탈로그 밖 도시도
    동작), 비활성/실패하면 큐레이션 카탈로그(lookup_nearby)로 폴백한다.
    """

    def run(self, state: TripPlanState) -> TripPlanState:
        brief = state.brief
        destination = state.selected_destination or (
            brief.destinations[0] if brief and brief.destinations else None
        )
        if not destination:
            return state
        guide = curate_nearby(destination) or lookup_nearby(destination)
        if guide is not None:
            state.nearby_guide = guide
        return state
