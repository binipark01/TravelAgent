from __future__ import annotations

from travel_agent.app.agents.flight_live_search import extract_live_flight_options
from travel_agent.app.providers.base import FlightProvider
from travel_agent.app.schemas.providers import FlightSearchRequest
from travel_agent.app.schemas.trip import TripPlanState


class FlightAgent:
    def __init__(
        self,
        provider: FlightProvider,
        *,
        live_enabled: bool = False,
        live_timeout: int = 40,
    ) -> None:
        self.provider = provider
        self.live_enabled = live_enabled
        self.live_timeout = live_timeout

    def run(self, state: TripPlanState) -> TripPlanState:
        brief = state.brief
        if not brief or not brief.origin or not state.selected_destination or not brief.start_date:
            return state

        # 실시간: 네이버 항공권 화면을 브라우저로 분석해 실제 운임만 사용한다.
        # 못 가져오면 mock으로 채우지 않고 비워 둔다(mock은 사용자에게 노출 금지).
        if self.live_enabled:
            if state.selected_destination and not brief.selected_destination:
                brief.selected_destination = state.selected_destination
            state.transport_options = extract_live_flight_options(
                brief,
                currency=state.currency,
                timeout_seconds=self.live_timeout,
                request_text=state.raw_user_message,
            )
            return state

        # live가 꺼진 경우(테스트 등)에만 결정론적 mock을 사용한다.
        request = FlightSearchRequest(
            origin=brief.origin,
            destination=state.selected_destination,
            departure_date=brief.start_date,
            return_date=brief.end_date,
            travelers=brief.travelers or 1,
            currency=state.currency,
            outbound_departure_window=(
                "morning" if "outbound_morning" in (brief.transport_preference or "") else None
            ),
            return_departure_window=(
                "afternoon" if "return_afternoon" in (brief.transport_preference or "") else None
            ),
        )
        state.transport_options = self.provider.search_flights(request)
        return state
