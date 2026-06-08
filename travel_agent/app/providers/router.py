from __future__ import annotations

from dataclasses import dataclass

from travel_agent.app.config import Settings
from travel_agent.app.connectors.errors import ProviderConfigurationError
from travel_agent.app.providers.base import ProviderBundle, build_mock_provider_bundle


@dataclass(frozen=True)
class ProviderRouter:
    settings: Settings

    def bundle(self) -> ProviderBundle:
        if self.settings.enable_live_providers and not self.settings.provider_fallback_to_mock:
            raise ProviderConfigurationError(
                "Live providers are enabled but no live provider bundle is configured."
            )
        # MVP/dev uses explicit mock providers and downstream evidence marks them as mock.
        return build_mock_provider_bundle()
