from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import Field

from travel_agent.app.schemas.common import StrictBaseModel
from travel_agent.app.schemas.trip import TripPlanState


class AgentResultStatus(StrEnum):
    completed = "completed"
    failed = "failed"
    skipped = "skipped"
    waiting_for_user = "waiting_for_user"


class MissingField(StrictBaseModel):
    field: str
    question: str
    reason: str
    critical: bool = False


class AgentResult(StrictBaseModel):
    agent_name: str
    status: AgentResultStatus
    state_patch: dict = Field(default_factory=dict)
    missing_fields: list[MissingField] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    tool_calls: list[dict] = Field(default_factory=list)
    output_summary: str | None = None
    error_message: str | None = None


class SupervisorAction(StrEnum):
    run_agent = "run_agent"
    run_agents_parallel = "run_agents_parallel"
    wait_for_user = "wait_for_user"
    replan = "replan"
    present_final = "present_final"
    fail = "fail"


class SupervisorDecision(StrictBaseModel):
    action: SupervisorAction
    agents: list[str] = Field(default_factory=list)
    reason: str
    questions: list[str] = Field(default_factory=list)


class BaseAgent(Protocol):
    name: str
    domain: str

    def required_state_fields(self, state: TripPlanState) -> list[MissingField]: ...

    def run(self, ctx, state: TripPlanState) -> AgentResult: ...
