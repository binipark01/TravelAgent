from __future__ import annotations

from travel_agent.app.llm.curator import curate_stay_areas
from travel_agent.app.schemas.trip import TripPlanState


class StayAreaAgent:
    """'어느 동네에 묵을지' 추천 숙박 구역을 LLM 웹검색으로 채운다.

    호텔 후보(가격·실재)와 별개로, 사용자가 동네를 모르는 비아시아권에서 특히 유용하다.
    LLM 웹검색이 꺼져 있거나 실패하면 비워 둔다(가격을 지어내지 않는 '판단' 정보).
    """

    def run(self, state: TripPlanState) -> TripPlanState:
        destination = state.primary_destination
        if not destination:
            return state
        guide = curate_stay_areas(destination)
        if guide is not None:
            state.stay_area_guide = guide
        return state
