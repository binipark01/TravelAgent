from __future__ import annotations

from travel_agent.app.connectors.places.google_places_browser import (
    detect_interest,
    extract_live_pois,
)
from travel_agent.app.llm.curator import curate_city_pois
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
            restaurants = extract_live_pois(
                state.selected_destination,
                currency=state.currency,
                kind="restaurant",
                interest=detect_interest(hint, "restaurant"),
                timeout_seconds=self.live_timeout,
            )
            attractions = extract_live_pois(
                state.selected_destination,
                currency=state.currency,
                kind="attraction",
                interest=detect_interest(hint, "attraction"),
                timeout_seconds=self.live_timeout,
            )
        else:
            # live가 꺼진 경우(테스트 등)에만 결정론적 mock 검색을 사용한다.
            request = PlacesSearchRequest(
                destination=state.selected_destination,
                interests=brief.must_include,
                currency=state.currency,
            )
            restaurants = self.provider.search_pois(request)
            attractions = []

        # LLM 웹검색 큐레이션: 별점순 구글 풀을 grounding으로 넘겨, 블로그·카페·관광청을
        # 종합해 재추천(이유·출처 포함)한다. 비활성/실패 시 구글/mock 결과를 그대로 쓴다.
        curated = curate_city_pois(
            state.selected_destination,
            interests=brief.must_include,
            start_date=brief.start_date,
            currency=state.currency,
            attraction_pool=attractions,
            restaurant_pool=restaurants,
        )
        if curated:
            state.poi_candidates = curated.restaurants or restaurants
            state.activity_options = curated.attractions or attractions
        else:
            state.poi_candidates = restaurants
            state.activity_options = attractions
        return state
