from __future__ import annotations

from travel_agent.app.sources.registry import SourceCandidate, SourceRegistry


class SourceDiscoveryTool:
    def __init__(self, registry: SourceRegistry) -> None:
        self.registry = registry

    def discover(self, domain: str) -> tuple[list[SourceCandidate], list[SourceCandidate]]:
        candidates = self.registry.get_candidates(domain)
        enabled = self.registry.get_enabled_sources(domain)
        rejected = [candidate for candidate in candidates if candidate not in enabled]
        return enabled, rejected
