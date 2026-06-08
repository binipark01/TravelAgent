from __future__ import annotations

from travel_agent.app.schemas.trip import TripPlanState


class DestinationDiscoveryAgent:
    def run(self, state: TripPlanState) -> TripPlanState:
        brief = state.brief
        if brief is None:
            return state
        if brief.destinations == ["Japan"]:
            candidates = ["Osaka", "Tokyo", "Fukuoka"]
        else:
            candidates = brief.destinations
        state.destination_candidates = candidates
        if state.selected_destination is None and candidates:
            food_or_shopping = {"food", "shopping"} & set(brief.must_include)
            state.selected_destination = (
                "Osaka" if "Osaka" in candidates and food_or_shopping else candidates[0]
            )
        return state
