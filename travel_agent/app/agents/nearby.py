from __future__ import annotations

from travel_agent.app.connectors.nearby.day_trips import lookup_nearby
from travel_agent.app.schemas.trip import TripPlanState


class NearbyAgent:
    """목적지 허브 기준 근교 당일치기 명소를 정리해 채운다(도시 데이터가 있을 때만)."""

    def run(self, state: TripPlanState) -> TripPlanState:
        brief = state.brief
        destination = state.selected_destination or (
            brief.destinations[0] if brief and brief.destinations else None
        )
        if not destination:
            return state
        guide = lookup_nearby(destination)
        if guide is not None:
            state.nearby_guide = guide
        return state
