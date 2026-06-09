from __future__ import annotations

from travel_agent.app.connectors.visa.entry_requirements import lookup_entry_requirements
from travel_agent.app.schemas.trip import TripPlanState


class VisaAgent:
    """목적지+국적 기준 입국 요건(무비자 기간·전자여행허가·여권 유효기간)을 채운다."""

    def run(self, state: TripPlanState) -> TripPlanState:
        brief = state.brief
        destination = state.selected_destination or (
            brief.destinations[0] if brief and brief.destinations else None
        )
        if not destination:
            return state
        passport = brief.passport_country if brief else None
        start = brief.start_date if brief else None
        end = brief.end_date if brief else None
        state.visa_result = lookup_entry_requirements(destination, passport, start, end)
        return state
