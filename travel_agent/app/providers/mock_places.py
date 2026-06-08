from __future__ import annotations

from travel_agent.app.providers.mock_common import mock_metadata
from travel_agent.app.schemas.common import Location, Money
from travel_agent.app.schemas.providers import PlacesSearchRequest, POIOption
from travel_agent.app.utils.ids import new_id


class MockPlacesProvider:
    provider_name = "mock_places"

    def search_pois(self, request: PlacesSearchRequest) -> list[POIOption]:
        destination = request.destination
        if destination in {"Tokyo", "도쿄"}:
            items = [
                ("Tsukiji Outer Market", "food", "Ginza", 25_000),
                ("Asakusa Sensoji", "culture", "Asakusa", 0),
                ("Shibuya Sky", "view", "Shibuya", 25_000),
                ("Harajuku Cat Street", "shopping", "Harajuku", 10_000),
                ("Shinjuku Izakaya Alley", "food", "Shinjuku", 45_000),
                ("TeamLab Planets", "experience", "Toyosu", 38_000),
            ]
        elif destination in {"Fukuoka", "후쿠오카"}:
            items = [
                ("Hakata Ramen Street", "food", "Hakata", 18_000),
                ("Ohori Park", "nature", "Ohori", 0),
                ("Canal City Hakata", "shopping", "Hakata", 15_000),
                ("Dazaifu Tenmangu", "culture", "Dazaifu", 5_000),
                ("Nakasu Yatai", "food", "Nakasu", 35_000),
                ("Momochi Seaside Park", "nature", "Momochi", 0),
            ]
        else:
            items = [
                ("Dotonbori Food Walk", "food", "Namba", 30_000),
                ("Kuromon Market", "food", "Namba", 25_000),
                ("Osaka Castle", "culture", "Chuo", 8_000),
                ("Umeda Sky Building", "view", "Umeda", 18_000),
                ("Shinsaibashi Shopping Street", "shopping", "Shinsaibashi", 15_000),
                ("Universal City Walk", "entertainment", "Bay Area", 20_000),
                ("Nara Day Trip", "culture", "Nara", 25_000),
            ]

        metadata = mock_metadata(self.provider_name, "Mock places search", "mock-poi")
        pois: list[POIOption] = []
        for title, poi_type, area, cost in items:
            pois.append(
                POIOption(
                    poi_id=new_id("poi"),
                    title=title,
                    type=poi_type,
                    location=Location(name=title, country="Japan", area=area),
                    area=area,
                    estimated_cost=Money(amount=cost, currency=request.currency),
                    opening_hours="10:00-21:00",
                    recommended_duration_minutes=120
                    if poi_type in {"experience", "culture"}
                    else 90,
                    booking_required=poi_type in {"experience", "view", "entertainment"},
                    metadata=metadata,
                    notes=["Mock POI details; opening hours require verification."],
                )
            )
        return pois
