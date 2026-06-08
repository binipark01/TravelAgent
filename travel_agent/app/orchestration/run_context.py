from __future__ import annotations

from dataclasses import dataclass

from travel_agent.app.config import Settings
from travel_agent.app.providers.base import ProviderBundle
from travel_agent.app.providers.router import ProviderRouter
from travel_agent.app.tools.accommodation_search import AccommodationSearchTool


@dataclass(frozen=True)
class RunContext:
    settings: Settings
    providers: ProviderBundle
    accommodation_search_tool: AccommodationSearchTool


def build_run_context(settings: Settings) -> RunContext:
    return RunContext(
        settings=settings,
        providers=ProviderRouter(settings).bundle(),
        accommodation_search_tool=AccommodationSearchTool(settings),
    )
