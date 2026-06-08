from __future__ import annotations

from travel_agent.app.orchestration.state_machine import append_source_refs
from travel_agent.app.providers.base import BookingProvider
from travel_agent.app.schemas.approvals import ApprovalRequest, ApprovalStatus, BookingRecord
from travel_agent.app.schemas.common import Money
from travel_agent.app.schemas.providers import BookingRequest
from travel_agent.app.schemas.trip import TripPlanState
from travel_agent.app.utils.time import utc_now


class BookingAssistantAgent:
    def __init__(self, provider: BookingProvider) -> None:
        self.provider = provider

    def run(
        self,
        state: TripPlanState,
        *,
        approval: ApprovalRequest,
        action_type: str,
        payload: dict,
        price: Money,
    ) -> BookingRecord:
        if approval.status != ApprovalStatus.approved:
            raise ValueError("A valid approved ApprovalRequest is required before booking.")
        result = self.provider.create_booking_stub(
            BookingRequest(
                action_type=action_type,
                payload=payload,
                price=price,
                approval_id=approval.approval_id,
            )
        )
        append_source_refs(state, [result.metadata.source_ref])
        record = BookingRecord(
            booking_id=result.booking_id,
            trip_id=state.trip_id,
            approval_id=approval.approval_id,
            action_type=action_type,
            provider_reference=result.provider_reference,
            simulated=True,
            status=result.status,
            price=price,
            created_at=utc_now(),
            notes=[
                "MVP simulated booking only; no real reservation, payment, or ticketing occurred."
            ],
        )
        state.booking_records.append(record)
        return record
