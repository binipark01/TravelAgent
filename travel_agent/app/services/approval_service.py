from __future__ import annotations

from sqlalchemy.orm import Session

from travel_agent.app.db.repositories import ApprovalRepository, TripRepository
from travel_agent.app.guardrails.approval_guardrail import approval_must_belong_to_trip
from travel_agent.app.orchestration.state_machine import add_audit_event
from travel_agent.app.schemas.approvals import (
    ApprovalCreateRequest,
    ApprovalRequest,
    ApprovalStatus,
)
from travel_agent.app.utils.hashing import payload_hash
from travel_agent.app.utils.ids import new_id
from travel_agent.app.utils.time import expires_in, utc_now


class ApprovalService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.trips = TripRepository(session)
        self.approvals = ApprovalRepository(session)

    def create(self, trip_id: str, request: ApprovalCreateRequest) -> ApprovalRequest:
        state = self.trips.load_latest_state(trip_id)
        approval = ApprovalRequest(
            approval_id=new_id("approval"),
            trip_id=trip_id,
            action_type=request.action_type,
            summary=request.summary,
            exact_payload_hash=payload_hash(request.payload),
            price_ceiling=request.price_ceiling,
            expires_at=expires_in(request.expires_in_hours),
            status=ApprovalStatus.pending,
        )
        state.approval_requests.append(approval)
        add_audit_event(state, "approval_created", f"Approval requested: {request.action_type}")
        self.approvals.add(approval)
        self.trips.save_snapshot(state)
        self.session.commit()
        return approval

    def approve(self, trip_id: str, approval_id: str) -> ApprovalRequest:
        state = self.trips.load_latest_state(trip_id)
        approval = self.approvals.get(approval_id)
        approval_must_belong_to_trip(trip_id, approval)
        approval.status = ApprovalStatus.approved
        approval.approved_at = utc_now()
        self._replace_state_approval(state, approval)
        add_audit_event(
            state, "approval_approved", f"Approval approved: {approval_id}", actor="user"
        )
        self.approvals.update(approval)
        self.trips.save_snapshot(state)
        self.session.commit()
        return approval

    def reject(self, trip_id: str, approval_id: str) -> ApprovalRequest:
        state = self.trips.load_latest_state(trip_id)
        approval = self.approvals.get(approval_id)
        approval_must_belong_to_trip(trip_id, approval)
        approval.status = ApprovalStatus.rejected
        approval.rejected_at = utc_now()
        self._replace_state_approval(state, approval)
        add_audit_event(
            state, "approval_rejected", f"Approval rejected: {approval_id}", actor="user"
        )
        self.approvals.update(approval)
        self.trips.save_snapshot(state)
        self.session.commit()
        return approval

    def list_for_trip(self, trip_id: str) -> list[ApprovalRequest]:
        self.trips.get_trip(trip_id)
        return self.approvals.list_for_trip(trip_id)

    def _replace_state_approval(self, state, approval: ApprovalRequest) -> None:
        state.approval_requests = [
            approval if item.approval_id == approval.approval_id else item
            for item in state.approval_requests
        ]
