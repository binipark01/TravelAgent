from __future__ import annotations

from sqlalchemy.orm import Session

from travel_agent.app.agent_core.runtime import AgentRuntime
from travel_agent.app.config import Settings, get_settings
from travel_agent.app.schemas.agent import (
    AgentEvent,
    AgentRunCreateRequest,
    AgentRunDetailResponse,
    AgentRunMessageRequest,
    AgentRunResponse,
    AgentRunSummary,
)
from travel_agent.app.schemas.itinerary import Itinerary


class AgentService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.runtime = AgentRuntime(session, self.settings)

    def create_run(self, request: AgentRunCreateRequest) -> AgentRunResponse:
        return self.runtime.start_run(
            request.message,
            user_id=request.user_id,
            locale=request.locale,
            currency=request.currency,
            timezone=request.timezone,
            history=request.history,
        )

    def begin_run(self, request: AgentRunCreateRequest) -> AgentRunResponse:
        """run을 만들고 run_id를 즉시 반환한다(실행은 execute_run이 백그라운드로)."""
        return self.runtime.begin_run(
            request.message,
            user_id=request.user_id,
            locale=request.locale,
            currency=request.currency,
            timezone=request.timezone,
            history=request.history,
        )

    def execute_run(self, run_id: str, *, message: str | None = None) -> AgentRunResponse:
        return self.runtime.execute_run(run_id, message=message)

    def begin_continue(self, run_id: str, message: str | None = None) -> AgentRunDetailResponse:
        """이어가기 턴을 준비하고(메시지 반영) 즉시 반환한다(실행은 execute_run)."""
        return self.runtime.begin_continue(run_id, message)

    def get_run(self, run_id: str) -> AgentRunDetailResponse:
        return self.runtime.get_run(run_id)

    def update_itinerary(self, run_id: str, itinerary: Itinerary) -> AgentRunDetailResponse:
        return self.runtime.update_itinerary(run_id, itinerary)

    def list_runs(self, limit: int = 30) -> list[AgentRunSummary]:
        return self.runtime.list_runs(limit)

    def add_message(self, run_id: str, request: AgentRunMessageRequest) -> AgentRunDetailResponse:
        return self.runtime.continue_run(run_id, request.message)

    def continue_run(self, run_id: str) -> AgentRunDetailResponse:
        return self.runtime.continue_run(run_id)

    def list_events(self, run_id: str) -> list[AgentEvent]:
        return self.runtime.get_events(run_id)
