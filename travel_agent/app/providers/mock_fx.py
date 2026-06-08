from __future__ import annotations

from travel_agent.app.providers.mock_common import mock_metadata
from travel_agent.app.schemas.providers import FxConversionRequest, FxConversionResult


class MockFxProvider:
    provider_name = "mock_fx"

    def convert(self, request: FxConversionRequest) -> FxConversionResult:
        rate = 1.0
        metadata = mock_metadata(self.provider_name, "Mock FX conversion", "mock-fx")
        return FxConversionResult(
            amount=request.amount,
            from_currency=request.from_currency,
            converted_amount=request.amount * rate,
            to_currency=request.to_currency,
            rate=rate,
            metadata=metadata,
        )
