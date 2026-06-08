from __future__ import annotations

from travel_agent.app.schemas.trip import TripPlanState


class UserProfileAgent:
    def run(self, state: TripPlanState) -> TripPlanState:
        brief = state.brief
        state.user_profile_snapshot = {
            "user_id": state.user_id,
            "locale": state.locale,
            "currency": state.currency,
            "travel_style": brief.travel_style if brief else None,
            "dietary_restrictions": brief.dietary_restrictions if brief else [],
        }
        return state
