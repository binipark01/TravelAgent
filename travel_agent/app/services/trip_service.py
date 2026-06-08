from __future__ import annotations

from sqlalchemy.orm import Session

from travel_agent.app.agents.supervisor import TravelSupervisorAgent
from travel_agent.app.config import Settings, get_settings
from travel_agent.app.db.repositories import TripRepository
from travel_agent.app.orchestration.run_context import build_run_context
from travel_agent.app.orchestration.state_machine import add_audit_event, questions_for_missing
from travel_agent.app.schemas.trip import (
    FinalPlanResponse,
    TripCreateRequest,
    TripMessageRequest,
    TripPlanState,
    TripSummaryResponse,
)
from travel_agent.app.utils.ids import new_id


class TripService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repository = TripRepository(session)
        self.supervisor = TravelSupervisorAgent(build_run_context(self.settings))

    def create_trip(self, request: TripCreateRequest) -> TripSummaryResponse:
        state = TripPlanState(
            trip_id=new_id("trip"),
            user_id=request.user_id,
            locale=request.locale,
            currency=request.currency,
            timezone=request.timezone,
            raw_user_message=request.message,
        )
        add_audit_event(state, "trip_created", "Trip intake started.", actor="user")
        self.supervisor.run_intake(state)
        self.repository.create_trip(state)
        self.session.commit()
        return self._summary_response(state)

    def get_state(self, trip_id: str) -> TripPlanState:
        return self.repository.load_latest_state(trip_id)

    def add_message(self, trip_id: str, request: TripMessageRequest) -> TripSummaryResponse:
        state = self.get_state(trip_id)
        state.raw_user_message = f"{state.raw_user_message}\n{request.message}"
        add_audit_event(
            state, "message_added", "User supplied additional trip details.", actor="user"
        )
        self.supervisor.run_intake(state, message=request.message)
        self.repository.save_snapshot(state)
        self.session.commit()
        return self._summary_response(state)

    def plan(self, trip_id: str) -> FinalPlanResponse:
        state = self.get_state(trip_id)
        response = self.supervisor.run_planning(state)
        self.repository.save_snapshot(state)
        self.session.commit()
        return response

    def validate(self, trip_id: str) -> TripPlanState:
        state = self.get_state(trip_id)
        self.supervisor.validate(state)
        self.repository.save_snapshot(state)
        self.session.commit()
        return state

    def _summary_response(self, state: TripPlanState) -> TripSummaryResponse:
        return TripSummaryResponse(
            trip_id=state.trip_id,
            status=state.status,
            summary="Trip intake updated.",
            missing_fields=state.missing_fields,
            questions=questions_for_missing(state.missing_fields),
            state=state,
        )
