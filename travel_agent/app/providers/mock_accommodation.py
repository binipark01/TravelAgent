from __future__ import annotations

from travel_agent.app.providers.mock_common import mock_metadata
from travel_agent.app.schemas.common import Location, Money
from travel_agent.app.schemas.providers import AccommodationOption, AccommodationSearchRequest
from travel_agent.app.utils.ids import new_id


class MockAccommodationProvider:
    provider_name = "mock_accommodation"

    def search_accommodations(
        self, request: AccommodationSearchRequest
    ) -> list[AccommodationOption]:
        nights = max((request.check_out - request.check_in).days, 1)
        nightly = 150_000 if request.destination in {"Osaka", "오사카"} else 135_000
        metadata = mock_metadata(self.provider_name, "Mock accommodation search", "mock-hotel")
        return [
            AccommodationOption(
                option_id=new_id("acc"),
                name=f"{request.destination} Mock Central Hotel",
                location=Location(
                    name=f"{request.destination} Station", country="Japan", area="Central"
                ),
                nightly_price=Money(amount=nightly, currency=request.currency),
                total_price=Money(amount=nightly * nights, currency=request.currency),
                rating=4.2,
                cancellation_policy="Simulated flexible cancellation until 48h before check-in.",
                metadata=metadata,
                notes=["Mock availability only; verify hotel terms before booking."],
            )
        ]
