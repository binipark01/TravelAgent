from __future__ import annotations

from travel_agent.app.connectors.places.google_places_browser import extract_live_pois
from travel_agent.app.providers.base import PlacesProvider
from travel_agent.app.schemas.providers import PlacesSearchRequest
from travel_agent.app.schemas.trip import TripPlanState


class RestaurantAgent:
    def __init__(
        self,
        provider: PlacesProvider,
        *,
        live_enabled: bool = False,
        live_timeout: int = 35,
    ) -> None:
        self.provider = provider
        self.live_enabled = live_enabled
        self.live_timeout = live_timeout

    def run(self, state: TripPlanState) -> TripPlanState:
        brief = state.brief
        if not brief or not state.selected_destination:
            return state

        # 실시간: 구글 지도 맛집 검색 화면을 브라우저로 분석해 실제 장소만 사용한다.
        # 못 가져오면 mock으로 채우지 않고 비워 둔다(mock은 사용자에게 노출 금지).
        if self.live_enabled:
            state.poi_candidates = extract_live_pois(
                state.selected_destination,
                currency=state.currency,
                timeout_seconds=self.live_timeout,
            )
            return state

        # live가 꺼진 경우(테스트 등)에만 결정론적 mock 검색을 사용한다.
        request = PlacesSearchRequest(
            destination=state.selected_destination,
            interests=brief.must_include,
            currency=state.currency,
        )
        state.poi_candidates = self.provider.search_pois(request)
        return state
