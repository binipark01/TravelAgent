from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from travel_agent.app.schemas.common import StrictBaseModel
from travel_agent.app.schemas.trip import TripPlanState


class AgentRunStatus(StrEnum):
    queued = "queued"
    running = "running"
    waiting_for_user = "waiting_for_user"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class AgentStepStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class AgentEventType(StrEnum):
    user_message = "user_message"
    agent_started = "agent_started"
    agent_completed = "agent_completed"
    agent_failed = "agent_failed"
    agent_skipped = "agent_skipped"
    tool_call_started = "tool_call_started"
    tool_call_completed = "tool_call_completed"
    source_discovered = "source_discovered"
    source_rejected = "source_rejected"
    evidence_collected = "evidence_collected"
    evidence_normalized = "evidence_normalized"
    evidence_ranked = "evidence_ranked"
    core_plan_decided = "core_plan_decided"
    missing_info_detected = "missing_info_detected"
    critic_blocker_found = "critic_blocker_found"
    approval_required = "approval_required"
    plan_ready = "plan_ready"
    run_waiting_for_user = "run_waiting_for_user"
    run_completed = "run_completed"
    error = "error"


class AgentRunCreateRequest(StrictBaseModel):
    message: str
    user_id: str | None = None
    locale: str = "ko-KR"
    currency: str = "KRW"
    timezone: str = "Asia/Seoul"
    # 이전 사용자 메시지들(과거→최근 순, 현재 message 제외). 대화 문맥 연속용.
    history: list[str] = Field(default_factory=list)


class AgentRunMessageRequest(StrictBaseModel):
    message: str


class AgentRun(StrictBaseModel):
    run_id: str
    trip_id: str
    status: AgentRunStatus
    current_step: str | None = None
    created_at: datetime | None = None
    started_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None


class AgentStep(StrictBaseModel):
    step_id: str
    run_id: str
    trip_id: str | None = None
    agent_name: str
    status: AgentStepStatus
    input_summary: str
    output_summary: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)


class AgentEvent(StrictBaseModel):
    event_id: str
    run_id: str
    trip_id: str
    type: AgentEventType
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class TripStateSummary(StrictBaseModel):
    destination: str | None = None
    origin: str | None = None
    date_range: str | None = None
    travelers: int | None = None
    budget_total: float | None = None
    budget_per_person: float | None = None
    status: str
    missing_fields: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class AgentRunResponse(StrictBaseModel):
    trip_id: str
    run_id: str
    status: AgentRunStatus
    current_step: str | None = None
    steps: list[AgentStep] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    state_summary: TripStateSummary | None = None
    partial_plan: TripPlanState | None = None
    events: list[AgentEvent] = Field(default_factory=list)


class AgentRunDetailResponse(StrictBaseModel):
    run: AgentRun
    steps: list[AgentStep]
    events: list[AgentEvent]
    state_summary: TripStateSummary
    state: TripPlanState


class AgentRunSummary(StrictBaseModel):
    """저장된 실행 목록('내 여행')용 요약."""

    run_id: str
    trip_id: str
    status: AgentRunStatus
    created_at: datetime
    message: str
    destination: str | None = None
    date_range: str | None = None
