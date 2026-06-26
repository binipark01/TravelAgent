from __future__ import annotations

from travel_agent.app.connectors.transport_tickets.booking_links import build_transport_tickets
from travel_agent.app.connectors.weather.open_meteo import geocode
from travel_agent.app.schemas.trip import TripPlanState


class TransportTicketsAgent:
    """교통권 예매 플랫폼·패스·구간 경로 딥링크를 채운다.

    현지교통(허브 도시)·근교(당일치기 명소) 결과가 있으면 그걸 구간 경로 링크에 쓴다.
    현지교통·근교 에이전트 다음에 실행한다.
    """

    def run(self, state: TripPlanState) -> TripPlanState:
        destination = state.primary_destination
        if not destination:
            return state

        hub_city = state.local_transport.city if state.local_transport else None
        hub = hub_city or destination.split(",")[0].strip()
        nearby = (
            [dest.name for dest in state.nearby_guide.destinations]
            if state.nearby_guide
            else None
        )
        # 키 없는 OSM 지도 중심용 좌표(Open-Meteo 지오코딩, 실패해도 무방).
        hub_lat = hub_lng = None
        try:
            coords = geocode(hub)
            if coords:
                hub_lat, hub_lng = coords
        except (OSError, ValueError):
            pass
        guide = build_transport_tickets(
            destination,
            hub_city=hub,
            airport_label=f"{hub} 공항",
            nearby=nearby,
            hub_lat=hub_lat,
            hub_lng=hub_lng,
        )
        if guide is not None:
            state.transport_tickets = guide
        return state
