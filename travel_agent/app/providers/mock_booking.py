from __future__ import annotations

from travel_agent.app.providers.mock_common import mock_metadata
from travel_agent.app.schemas.providers import BookingProviderResult, BookingRequest
from travel_agent.app.utils.ids import new_id


class MockBookingProvider:
    provider_name = "mock_booking"

    def create_booking_stub(self, request: BookingRequest) -> BookingProviderResult:
        metadata = mock_metadata(self.provider_name, "Mock booking stub", "mock-booking")
        return BookingProviderResult(
            booking_id=new_id("book"),
            provider_reference=f"SIM-{new_id('ref')}",
            simulated=True,
            status="simulated_confirmed",
            metadata=metadata,
        )
