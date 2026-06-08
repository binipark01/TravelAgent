from __future__ import annotations

from travel_agent.app.connectors.places.google_places_browser import (
    detect_interest,
    extract_live_pois,
)
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

        # 실시간: 구글 지도에서 맛집 + 관광지를 브라우저로 분석해 실제 장소만 사용한다.
        # 못 가져오면 mock으로 채우지 않고 비워 둔다(mock은 사용자에게 노출 금지).
        if self.live_enabled:
            # 사용자가 명시한 취향(스시·박물관 등)을 검색에 반영한다.
            hint = " ".join([state.raw_user_message or "", *brief.must_include])
            state.poi_candidates = extract_live_pois(
                state.selected_destination,
                currency=state.currency,
                kind="restaurant",
                interest=detect_interest(hint, "restaurant"),
                timeout_seconds=self.live_timeout,
            )
            state.activity_options = extract_live_pois(
                state.selected_destination,
                currency=state.currency,
                kind="attraction",
                interest=detect_interest(hint, "attraction"),
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
