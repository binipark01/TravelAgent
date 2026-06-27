from __future__ import annotations

from travel_agent.app.connectors.routes.local_transport import lookup_local_transport
from travel_agent.app.llm.curator import curate_local_transport
from travel_agent.app.schemas.trip import TripPlanState


class LocalTransportAgent:
    """공항↔시내 교통 + 교통패스 안내를 채운다.

    먼저 큐레이션 정적 데이터(아시아 주요 도시)를 보고, 없으면 LLM 웹검색으로 폴백한다
    (유럽·미국 등 정적 데이터 밖 도시도 카드가 비지 않게).
    """

    def run(self, state: TripPlanState) -> TripPlanState:
        destination = state.primary_destination
        if not destination:
            return state
        plan = lookup_local_transport(destination)
        if plan is None:
            country = (
                state.visa_result.destination_country if state.visa_result else None
            )
            plan = curate_local_transport(destination, country)
        if plan is not None:
            state.local_transport = plan
        return state
