from __future__ import annotations

from travel_agent.app.providers.mock_common import mock_metadata
from travel_agent.app.schemas.providers import RouteLeg, RouteMatrixRequest


class MockRoutesProvider:
    provider_name = "mock_routes"

    def compute_route_matrix(self, request: RouteMatrixRequest) -> list[RouteLeg]:
        metadata = mock_metadata(self.provider_name, "Mock route matrix", "mock-route")
        legs: list[RouteLeg] = []
        for origin, destination in zip(request.locations, request.locations[1:], strict=False):
            same_area = origin.area and destination.area and origin.area == destination.area
            travel_minutes = 15 if same_area else 35
            legs.append(
                RouteLeg(
                    origin=origin.name,
                    destination=destination.name,
                    travel_minutes=travel_minutes,
                    mode="transit",
                    distance_km=2.5 if same_area else 8.0,
                    metadata=metadata,
                )
            )
        return legs
