from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from travel_agent.app.db.session import get_db, get_session_factory
from travel_agent.app.schemas.agent import (
    AgentEvent,
    AgentRunCreateRequest,
    AgentRunDetailResponse,
    AgentRunMessageRequest,
    AgentRunResponse,
    AgentRunSummary,
)
from travel_agent.app.schemas.itinerary import Itinerary
from travel_agent.app.services.agent_service import AgentService

router = APIRouter(prefix="/agent/runs", tags=["agent"])


def _execute_run_in_background(run_id: str, message: str | None) -> None:
    """응답을 보낸 뒤 자체 세션에서 무거운 실행을 수행한다(요청 세션은 이미 닫힘)."""
    factory = get_session_factory()
    with factory() as session:
        AgentService(session).execute_run(run_id, message=message)


@router.post("", response_model=AgentRunResponse)
def create_agent_run(
    request: AgentRunCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> AgentRunResponse:
    # run_id를 즉시 돌려주고, 실제 계획 수립은 백그라운드에서. 프론트는 GET으로 폴링.
    response = AgentService(db).begin_run(request)
    background_tasks.add_task(_execute_run_in_background, response.run_id, None)
    return response


@router.get("", response_model=list[AgentRunSummary])
def list_agent_runs(limit: int = 30, db: Session = Depends(get_db)) -> list[AgentRunSummary]:
    return AgentService(db).list_runs(limit)


@router.get("/{run_id}", response_model=AgentRunDetailResponse)
def get_agent_run(run_id: str, db: Session = Depends(get_db)) -> AgentRunDetailResponse:
    return AgentService(db).get_run(run_id)


@router.post("/{run_id}/messages", response_model=AgentRunDetailResponse)
def add_agent_message(
    run_id: str,
    request: AgentRunMessageRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> AgentRunDetailResponse:
    # 이어가기 턴도 즉시 반환 + 백그라운드 실행 → 프론트가 같은 run을 폴링.
    detail = AgentService(db).begin_continue(run_id, request.message)
    background_tasks.add_task(_execute_run_in_background, run_id, request.message)
    return detail


@router.post("/{run_id}/continue", response_model=AgentRunDetailResponse)
def continue_agent_run(run_id: str, db: Session = Depends(get_db)) -> AgentRunDetailResponse:
    return AgentService(db).continue_run(run_id)


@router.post("/{run_id}/cancel", response_model=AgentRunDetailResponse)
def cancel_agent_run(run_id: str, db: Session = Depends(get_db)) -> AgentRunDetailResponse:
    # 실행 중지: 협조적 취소 플래그 + 상태를 cancelled로. 백그라운드 실행은 다음 단계에서 멈춘다.
    return AgentService(db).cancel_run(run_id)


@router.post("/{run_id}/itinerary", response_model=AgentRunDetailResponse)
def update_agent_itinerary(
    run_id: str, itinerary: Itinerary, db: Session = Depends(get_db)
) -> AgentRunDetailResponse:
    # 사용자가 화면에서 직접 편집한 일정(드래그·삭제·시간)을 저장.
    return AgentService(db).update_itinerary(run_id, itinerary)


@router.get("/{run_id}/events", response_model=list[AgentEvent])
def get_agent_events(run_id: str, db: Session = Depends(get_db)) -> list[AgentEvent]:
    return AgentService(db).list_events(run_id)
