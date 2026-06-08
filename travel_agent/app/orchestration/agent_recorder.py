from __future__ import annotations

from typing import Protocol


class AgentRunRecorder(Protocol):
    def start_step(self, agent_name: str, input_summary: str) -> str: ...

    def complete_step(
        self,
        step_id: str,
        output_summary: str,
        tool_calls: list[dict] | None = None,
    ) -> None: ...

    def skip_step(self, agent_name: str, reason: str) -> None: ...

    def fail_step(self, step_id: str, reason: str) -> None: ...

    def event(self, event_type: str, message: str, payload: dict | None = None) -> None: ...
