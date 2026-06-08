from __future__ import annotations

from sqlalchemy.orm import Session

from travel_agent.app.agents.booking import BookingAssistantAgent
from travel_agent.app.config import get_settings
from travel_agent.app.db.repositories import ApprovalRepository, BookingRepository, TripRepository
from travel_agent.app.guardrails.approval_guardrail import (
    GuardrailViolation,
    approval_must_be_valid,
    approval_must_belong_to_trip,
    approval_required_for_side_effects,
    cancellation_policy_must_be_acknowledged,
    no_booking_if_missing_traveler_identity,
    no_sensitive_data_persistence_without_consent,
    payload_hash_must_match_approval,
    price_must_not_exceed_approval_ceiling,
)
from travel_agent.app.orchestration.run_context import build_run_context
from travel_agent.app.orchestration.state_machine import add_audit_event
from travel_agent.app.schemas.approvals import BookingRecord, BookingSimulationRequest


class BookingService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.trips = TripRepository(session)
        self.approvals = ApprovalRepository(session)
        self.bookings = BookingRepository(session)
        self.agent = BookingAssistantAgent(build_run_context(get_settings()).providers.booking)

    def simulate(self, trip_id: str, request: BookingSimulationRequest) -> BookingRecord:
        state = self.trips.load_latest_state(trip_id)
        approval = self.approvals.get(request.approval_id) if request.approval_id else None
        approval_required_for_side_effects(request.action_type, approval)
        if approval is None:
            raise GuardrailViolation("Approval is required.")
        approval_must_belong_to_trip(trip_id, approval)
        approval_must_be_valid(approval)
        payload_hash_must_match_approval(request.payload, approval)
        price_must_not_exceed_approval_ceiling(request.price, approval)
        cancellation_policy_must_be_acknowledged(request.cancellation_policy_acknowledged)
        no_booking_if_missing_traveler_identity(state, request.payload)
        no_sensitive_data_persistence_without_consent(request.payload)
        record = self.agent.run(
            state,
            approval=approval,
            action_type=request.action_type,
            payload=request.payload,
            price=request.price,
        )
        add_audit_event(
            state,
            "booking_simulated",
            "Simulated booking created after approval guardrails passed.",
        )
        self.bookings.add(record)
        self.trips.save_snapshot(state)
        self.session.commit()
        return record
