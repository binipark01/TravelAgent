from __future__ import annotations

from dataclasses import dataclass

from travel_agent.app.agent_core.checkpoint import CheckpointStore
from travel_agent.app.agent_core.event_bus import EventBus
from travel_agent.app.config import Settings
from travel_agent.app.evidence.store import EvidenceStore
from travel_agent.app.providers.router import ProviderRouter
from travel_agent.app.sources.registry import SourceRegistry
from travel_agent.app.tools.travel_tools import ToolExecutor


@dataclass
class RunContext:
    run_id: str
    trip_id: str
    user_id: str | None
    locale: str
    currency: str
    timezone: str
    provider_router: ProviderRouter
    source_registry: SourceRegistry
    tool_executor: ToolExecutor
    event_bus: EventBus
    checkpoint_store: CheckpointStore
    evidence_store: EvidenceStore
    guardrail_executor: object | None
    llm_client: object | None
    max_replan_attempts: int = 2
    dry_run: bool = True
    settings: Settings | None = None
