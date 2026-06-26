from __future__ import annotations

from travel_agent.app.connectors.safety.advisories import lookup_safety_info
from travel_agent.app.schemas.trip import TripPlanState


class SafetyAgent:
    """긴급연락처·영사콜센터·여행경보·보험/주의사항을 채운다(도시 데이터가 있을 때만)."""

    def run(self, state: TripPlanState) -> TripPlanState:
        destination = state.primary_destination
        if not destination:
            return state
        info = lookup_safety_info(destination)
        if info is not None:
            state.safety_info = info
        return state
