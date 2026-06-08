from __future__ import annotations

from travel_agent.app.db.repositories import AgentRunRepository
from travel_agent.app.schemas.agent import AgentEvent, AgentEventType
from travel_agent.app.utils.ids import new_id
from travel_agent.app.utils.time import utc_now


class EventBus:
    def __init__(self, repository: AgentRunRepository, *, run_id: str, trip_id: str) -> None:
        self.repository = repository
        self.run_id = run_id
        self.trip_id = trip_id

    def emit(
        self, event_type: AgentEventType | str, message: str, payload: dict | None = None
    ) -> None:
        self.repository.add_event(
            AgentEvent(
                event_id=new_id("event"),
                run_id=self.run_id,
                trip_id=self.trip_id,
                type=AgentEventType(event_type),
                message=message,
                payload=payload or {},
                created_at=utc_now(),
            )
        )
