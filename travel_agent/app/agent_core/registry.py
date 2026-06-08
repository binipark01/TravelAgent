from __future__ import annotations

from travel_agent.app.agent_core.contracts import BaseAgent


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        self._agents[agent.name] = agent

    def get(self, name: str) -> BaseAgent:
        return self._agents[name]

    def names(self) -> list[str]:
        return list(self._agents)
