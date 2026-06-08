from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from travel_agent.app.db.session import get_db
from travel_agent.app.schemas.common import CriticFinding
from travel_agent.app.schemas.trip import (
    FinalPlanResponse,
    TripCreateRequest,
    TripMessageRequest,
    TripSummaryResponse,
)
from travel_agent.app.services.trip_service import TripService

router = APIRouter(prefix="/trips", tags=["trips"])


@router.post("", response_model=TripSummaryResponse)
def create_trip(request: TripCreateRequest, db: Session = Depends(get_db)) -> TripSummaryResponse:
    return TripService(db).create_trip(request)


@router.get("/{trip_id}", response_model=TripSummaryResponse)
def get_trip(trip_id: str, db: Session = Depends(get_db)) -> TripSummaryResponse:
    service = TripService(db)
    state = service.get_state(trip_id)
    return TripSummaryResponse(
        trip_id=state.trip_id,
        status=state.status,
        summary="Current trip state.",
        missing_fields=state.missing_fields,
        questions=[],
        state=state,
    )


@router.post("/{trip_id}/messages", response_model=TripSummaryResponse)
def add_message(
    trip_id: str, request: TripMessageRequest, db: Session = Depends(get_db)
) -> TripSummaryResponse:
    return TripService(db).add_message(trip_id, request)


@router.post("/{trip_id}/plan", response_model=FinalPlanResponse)
def plan_trip(trip_id: str, db: Session = Depends(get_db)) -> FinalPlanResponse:
    return TripService(db).plan(trip_id)


@router.post("/{trip_id}/validate", response_model=list[CriticFinding])
def validate_trip(trip_id: str, db: Session = Depends(get_db)) -> list[CriticFinding]:
    state = TripService(db).validate(trip_id)
    return state.critic_findings
