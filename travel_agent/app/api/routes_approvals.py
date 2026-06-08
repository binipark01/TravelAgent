from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from travel_agent.app.db.session import get_db
from travel_agent.app.schemas.approvals import (
    ApprovalCreateRequest,
    ApprovalRequest,
    BookingRecord,
    BookingSimulationRequest,
)
from travel_agent.app.services.approval_service import ApprovalService
from travel_agent.app.services.booking_service import BookingService

router = APIRouter(prefix="/trips/{trip_id}", tags=["approvals"])


@router.post("/approvals", response_model=ApprovalRequest)
def create_approval(
    trip_id: str,
    request: ApprovalCreateRequest,
    db: Session = Depends(get_db),
) -> ApprovalRequest:
    return ApprovalService(db).create(trip_id, request)


@router.get("/approvals", response_model=list[ApprovalRequest])
def list_approvals(trip_id: str, db: Session = Depends(get_db)) -> list[ApprovalRequest]:
    return ApprovalService(db).list_for_trip(trip_id)


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalRequest)
def approve_approval(
    trip_id: str,
    approval_id: str,
    db: Session = Depends(get_db),
) -> ApprovalRequest:
    return ApprovalService(db).approve(trip_id, approval_id)


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalRequest)
def reject_approval(
    trip_id: str,
    approval_id: str,
    db: Session = Depends(get_db),
) -> ApprovalRequest:
    return ApprovalService(db).reject(trip_id, approval_id)


@router.post("/bookings/simulate", response_model=BookingRecord)
def simulate_booking(
    trip_id: str,
    request: BookingSimulationRequest,
    db: Session = Depends(get_db),
) -> BookingRecord:
    return BookingService(db).simulate(trip_id, request)
