from __future__ import annotations

from travel_agent.app.llm.curator import curate_checklist
from travel_agent.app.schemas.trip import TripPlanState


class ChecklistAgent:
    """출발 전 준비물·할 일 체크리스트를 LLM으로 채운다.

    비자·환율 등 이미 수집한 정보를 맥락으로 넘겨 목적지·계절에 맞춘 체크리스트를 만든다.
    LLM이 꺼져 있으면 비워 둔다.
    """

    def run(self, state: TripPlanState) -> TripPlanState:
        brief = state.brief
        destination = state.selected_destination or (
            brief.destinations[0] if brief and brief.destinations else None
        )
        if not destination:
            return state
        checklist = curate_checklist(destination, context=self._context(state, destination))
        if checklist is not None:
            state.prep_checklist = checklist
        return state

    @staticmethod
    def _context(state: TripPlanState, destination: str) -> str:
        brief = state.brief
        parts = [destination]
        if brief:
            if brief.start_date:
                parts.append(f"출발 {brief.start_date.isoformat()}")
            if brief.duration_days:
                parts.append(f"{brief.duration_days}일")
            if brief.travelers:
                parts.append(f"{brief.travelers}명")
            if brief.passport_country:
                parts.append(f"여권 {brief.passport_country}")
        if state.visa_result:
            parts.append(f"비자: {state.visa_result.summary}")
        if state.fx_info:
            parts.append(f"현지통화 {state.fx_info.target_currency}")
        return ", ".join(parts)
