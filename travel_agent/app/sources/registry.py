from __future__ import annotations

import os
from collections.abc import Mapping

from typing_extensions import TypedDict

from travel_agent.app.config import Settings
from travel_agent.app.sources.catalog import CATALOG, SourceCandidate
from travel_agent.app.sources.source_policy import SourcePolicy


class SourceStatus(TypedDict):
    domain: str
    name: str
    source_type: str
    connector: str
    status: str
    configured: bool
    enabled: bool
    missing_credentials: bool
    fallback_to_mock: bool
    reason: str


class SourceRegistry:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.policy = SourcePolicy(settings)

    def get_candidates(
        self, domain: str, config: Mapping[str, str] | None = None
    ) -> list[SourceCandidate]:
        requested = self._configured_sources(domain)
        candidates = list(CATALOG.get(domain, ()))
        if requested:
            order = {name: index for index, name in enumerate(requested)}
            candidates = [candidate for candidate in candidates if candidate.name in requested]
            candidates.sort(key=lambda candidate: order[candidate.name])
        return candidates

    def get_enabled_sources(
        self, domain: str, config: Mapping[str, str] | None = None
    ) -> list[SourceCandidate]:
        return [
            candidate
            for candidate in self.get_candidates(domain, config)
            if self.policy.evaluate(candidate).allowed
        ]

    def validate_credentials(self, source: SourceCandidate) -> bool:
        return all(os.getenv(name) for name in source.required_env)

    def explain_source_status(self, source: SourceCandidate) -> SourceStatus:
        decision = self.policy.evaluate(source)
        return {
            "domain": source.domain,
            "name": source.name,
            "source_type": source.source_type,
            "connector": source.connector,
            "configured": source in self.get_candidates(source.domain),
            "enabled": decision.allowed,
            "missing_credentials": bool(source.required_env)
            and not self.validate_credentials(source),
            "fallback_to_mock": self.settings.provider_fallback_to_mock,
            "status": "enabled" if decision.allowed else "disabled",
            "reason": decision.reason,
        }

    def status_for_domain(self, domain: str) -> list[SourceStatus]:
        return [
            self.explain_source_status(source)
            for source in self.get_candidates(domain)
        ]

    def all_status(self) -> list[SourceStatus]:
        return [
            self.explain_source_status(source)
            for domain in CATALOG
            for source in self.get_candidates(domain)
        ]

    def _configured_sources(self, domain: str) -> tuple[str, ...]:
        attr = {
            "flights": "flight_sources",
            "accommodations": "accommodation_sources",
            "places": "poi_sources",
            "routes": "route_sources",
            "activities": "activity_sources",
            "visa": "visa_sources",
            "safety": "safety_sources",
            "weather": "weather_sources",
            "fx": "fx_sources",
        }.get(domain)
        return getattr(self.settings, attr) if attr else ()
