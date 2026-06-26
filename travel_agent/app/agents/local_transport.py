from __future__ import annotations

from travel_agent.app.connectors.routes.local_transport import lookup_local_transport
from travel_agent.app.schemas.trip import TripPlanState


class LocalTransportAgent:
    """공항↔시내 교통 + 교통패스 안내를 채운다(도시 데이터가 있을 때만)."""

    def run(self, state: TripPlanState) -> TripPlanState:
        destination = state.primary_destination
        if not destination:
            return state
        plan = lookup_local_transport(destination)
        if plan is not None:
            state.local_transport = plan
        return state
