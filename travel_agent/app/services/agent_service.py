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
)


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

    def get_run(self, run_id: str) -> AgentRunDetailResponse:
        return self.runtime.get_run(run_id)

    def add_message(self, run_id: str, request: AgentRunMessageRequest) -> AgentRunDetailResponse:
        return self.runtime.continue_run(run_id, request.message)

    def continue_run(self, run_id: str) -> AgentRunDetailResponse:
        return self.runtime.continue_run(run_id)

    def list_events(self, run_id: str) -> list[AgentEvent]:
        return self.runtime.get_events(run_id)
