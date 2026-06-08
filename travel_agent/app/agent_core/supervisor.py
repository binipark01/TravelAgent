from __future__ import annotations

from travel_agent.app.agent_core.contracts import SupervisorAction, SupervisorDecision
from travel_agent.app.agent_core.graph import TRAVEL_PLANNING_GRAPH
from travel_agent.app.orchestration.state_machine import critical_missing_fields
from travel_agent.app.schemas.trip import TripPlanState


class TravelSupervisorAgent:
    name = "TravelSupervisorAgent"

    def decide(self, state: TripPlanState) -> SupervisorDecision:
        missing = critical_missing_fields(state)
        if missing:
            return SupervisorDecision(
                action=SupervisorAction.wait_for_user,
                reason="critical travel planning information is missing",
                questions=[self._question_for(field) for field in missing],
            )
        return SupervisorDecision(
            action=SupervisorAction.run_agents_parallel,
            agents=TRAVEL_PLANNING_GRAPH,
            reason="run evidence-driven travel planning graph",
        )

    def _question_for(self, field: str) -> str:
        return {
            "origin": "어디에서 출발하시나요?",
            "destinations": "어디로 가고 싶으신가요?",
            "start_date": "언제 출발하시나요?",
            "end_date": "언제 돌아오시나요?",
            "travelers": "몇 명이 여행하시나요?",
            "passport_country": "여권 국적은 어디인가요?",
        }.get(field, f"{field} 정보가 필요합니다.")
