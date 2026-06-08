from __future__ import annotations

from travel_agent.app.db.repositories import AgentRunRepository
from travel_agent.app.schemas.agent import AgentRunStatus, AgentStep, AgentStepStatus
from travel_agent.app.utils.ids import new_id
from travel_agent.app.utils.time import utc_now


class AgentStepExecutor:
    def __init__(self, repository: AgentRunRepository, *, run_id: str, trip_id: str) -> None:
        self.repository = repository
        self.run_id = run_id
        self.trip_id = trip_id

    def start(self, agent_name: str, input_summary: str) -> str:
        step_id = new_id("step")
        self.repository.update_run(
            self.run_id, status=AgentRunStatus.running, current_step=agent_name
        )
        self.repository.add_step(
            AgentStep(
                step_id=step_id,
                run_id=self.run_id,
                trip_id=self.trip_id,
                agent_name=agent_name,
                status=AgentStepStatus.running,
                input_summary=input_summary,
                started_at=utc_now(),
            )
        )
        return step_id

    def complete(
        self, step_id: str, output_summary: str, tool_calls: list[dict] | None = None
    ) -> None:
        self.repository.update_step(
            step_id,
            status=AgentStepStatus.completed,
            output_summary=output_summary,
            completed_at=utc_now(),
            tool_calls=tool_calls or [],
        )

    def skip(self, agent_name: str, reason: str) -> None:
        self.repository.add_step(
            AgentStep(
                step_id=new_id("step"),
                run_id=self.run_id,
                trip_id=self.trip_id,
                agent_name=agent_name,
                status=AgentStepStatus.skipped,
                input_summary=reason,
                output_summary=reason,
            )
        )

    def fail(self, step_id: str, reason: str) -> None:
        self.repository.update_step(
            step_id,
            status=AgentStepStatus.failed,
            output_summary=reason,
            completed_at=utc_now(),
            error_message=reason,
        )
