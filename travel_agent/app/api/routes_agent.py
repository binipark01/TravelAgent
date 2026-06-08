from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from travel_agent.app.db.session import get_db
from travel_agent.app.schemas.agent import (
    AgentEvent,
    AgentRunCreateRequest,
    AgentRunDetailResponse,
    AgentRunMessageRequest,
    AgentRunResponse,
)
from travel_agent.app.services.agent_service import AgentService

router = APIRouter(prefix="/agent/runs", tags=["agent"])


@router.post("", response_model=AgentRunResponse)
def create_agent_run(
    request: AgentRunCreateRequest, db: Session = Depends(get_db)
) -> AgentRunResponse:
    return AgentService(db).create_run(request)


@router.get("/{run_id}", response_model=AgentRunDetailResponse)
def get_agent_run(run_id: str, db: Session = Depends(get_db)) -> AgentRunDetailResponse:
    return AgentService(db).get_run(run_id)


@router.post("/{run_id}/messages", response_model=AgentRunDetailResponse)
def add_agent_message(
    run_id: str,
    request: AgentRunMessageRequest,
    db: Session = Depends(get_db),
) -> AgentRunDetailResponse:
    return AgentService(db).add_message(run_id, request)


@router.post("/{run_id}/continue", response_model=AgentRunDetailResponse)
def continue_agent_run(run_id: str, db: Session = Depends(get_db)) -> AgentRunDetailResponse:
    return AgentService(db).continue_run(run_id)


@router.get("/{run_id}/events", response_model=list[AgentEvent])
def get_agent_events(run_id: str, db: Session = Depends(get_db)) -> list[AgentEvent]:
    return AgentService(db).list_events(run_id)
