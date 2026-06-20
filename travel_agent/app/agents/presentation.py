from __future__ import annotations

from travel_agent.app.schemas.common import FindingSeverity
from travel_agent.app.schemas.trip import FinalPlanResponse, TripPlanState


class PresentationAgent:
    def build_final_response(self, state: TripPlanState) -> FinalPlanResponse:
        blocking = [f for f in state.critic_findings if f.severity == FindingSeverity.blocking]
        next_actions = []
        if blocking:
            next_actions.append("blocking critic finding을 해결한 뒤 최종 확정하세요.")
        if not state.approval_requests:
            next_actions.append(
                "예약/결제/메일/캘린더 같은 side effect는 별도 승인 없이는 실행되지 않습니다."
            )
        return FinalPlanResponse(
            trip_id=state.trip_id,
            status=state.status,
            summary=self._summary(state),
            assumptions=state.assumptions,
            missing_fields=state.missing_fields,
            recommended_destination=state.selected_destination,
            transport_options=state.transport_options,
            accommodation_options=state.accommodation_options,
            itinerary=state.optimized_itinerary,
            budget=state.budget,
            visa_result=state.visa_result,
            local_transport=state.local_transport,
            fx_info=state.fx_info,
            safety_info=state.safety_info,
            nearby_guide=state.nearby_guide,
            stay_area_guide=state.stay_area_guide,
            prep_checklist=state.prep_checklist,
            transport_tickets=state.transport_tickets,
            risk_findings=state.risk_findings,
            critic_findings=state.critic_findings,
            approval_requests=state.approval_requests,
            source_refs=state.source_refs,
            next_actions=next_actions,
        )

    def _summary(self, state: TripPlanState) -> str:
        destination = state.selected_destination or "목적지 미정"
        days = state.brief.duration_days if state.brief and state.brief.duration_days else "미정"
        return (
            f"{destination} {days}일 여행 계획 초안입니다. "
            "모든 가격과 가능 여부는 mock 데이터입니다."
        )
