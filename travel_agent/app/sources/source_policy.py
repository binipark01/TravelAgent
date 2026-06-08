from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from travel_agent.app.config import Settings

if TYPE_CHECKING:
    from travel_agent.app.sources.registry import SourceCandidate


@dataclass(frozen=True)
class SourcePolicyDecision:
    allowed: bool
    reason: str


class SourcePolicy:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def evaluate(self, source: SourceCandidate) -> SourcePolicyDecision:
        if source.status == "disabled_until_authorized" or source.source_type == "authorized_only":
            return SourcePolicyDecision(False, "source requires explicit authorization")
        if source.source_type == "mock":
            if not self.settings.enable_live_providers or self.settings.provider_fallback_to_mock:
                return SourcePolicyDecision(True, "mock allowed only for dev/test/fallback")
            return SourcePolicyDecision(False, "mock disabled when live providers are required")
        if not self.settings.enable_live_providers:
            return SourcePolicyDecision(False, "live providers disabled")
        if source.status == "enabled_by_default":
            return SourcePolicyDecision(True, "source enabled by default")
        missing = [name for name in source.required_env if not os.getenv(name)]
        if missing:
            return SourcePolicyDecision(False, "missing credentials")
        if source.source_type in {
            "official_api",
            "partner_api",
            "public_page",
        }:
            return SourcePolicyDecision(True, "source allowed by policy")
        return SourcePolicyDecision(False, "source type is not allowed")
