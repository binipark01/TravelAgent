from __future__ import annotations

from travel_agent.app.providers.mock_common import mock_metadata
from travel_agent.app.schemas.providers import VisaCheckRequest, VisaCheckResult


class MockVisaProvider:
    provider_name = "mock_visa"

    def check_entry_requirements(self, request: VisaCheckRequest) -> VisaCheckResult:
        missing = []
        if not request.passport_country:
            missing.append("passport_country")
        metadata = mock_metadata(self.provider_name, "Mock visa risk check", "mock-visa")
        summary = (
            "Mock placeholder: entry requirements must be verified with official sources "
            "before booking."
        )
        return VisaCheckResult(
            destination_country=request.destination_country,
            summary=summary,
            requires_official_verification=True,
            missing_required_info=missing,
            metadata=metadata,
        )
