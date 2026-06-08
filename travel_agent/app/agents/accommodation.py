from __future__ import annotations

from travel_agent.app.connectors.accommodations.naver_hotel_browser import (
    extract_live_accommodation_options,
)
from travel_agent.app.schemas.brief import TripBrief
from travel_agent.app.schemas.providers import AccommodationSearchRequest
from travel_agent.app.schemas.trip import TripPlanState
from travel_agent.app.tools.accommodation_search import AccommodationSearchTool


def _nightly_budget(brief: TripBrief) -> int | None:
    """예산을 1박 상한으로 해석한다('20안쪽'=20만원/박 같은 캡 의도)."""
    cap = brief.budget_per_person or brief.budget_total
    if not cap or cap <= 0:
        return None
    return int(cap)


def _stay_nights(brief: TripBrief) -> int:
    """숙박 일수를 정한다. 기간을 명시했으면 그 값을, 아니면 날짜 범위로 추정하되
    범위가 비정상적으로 넓으면(월 단위로 잡힌 경우) 기본값으로 제한한다."""
    if brief.duration_nights:
        return max(brief.duration_nights, 1)
    span = max((brief.end_date - brief.start_date).days, 1)
    return span if span <= 7 else 2


class AccommodationAgent:
    def __init__(
        self,
        tool: AccommodationSearchTool,
        *,
        live_enabled: bool = False,
        live_timeout: int = 35,
    ) -> None:
        self.tool = tool
        self.live_enabled = live_enabled
        self.live_timeout = live_timeout

    def run(self, state: TripPlanState) -> TripPlanState:
        brief = state.brief
        if (
            not brief
            or not state.selected_destination
            or not brief.start_date
            or not brief.end_date
        ):
            return state
        nights = _stay_nights(brief)

        # 실시간: 네이버 호텔 검색 화면을 브라우저로 분석해 실제 숙소만 사용한다.
        # 못 가져오면 mock으로 채우지 않고 비워 둔다(mock은 사용자에게 노출 금지).
        if self.live_enabled:
            state.accommodation_options = extract_live_accommodation_options(
                state.selected_destination,
                nights=nights,
                currency=state.currency,
                timeout_seconds=self.live_timeout,
                max_nightly_price=_nightly_budget(brief),
            )
            return state

        # live가 꺼진 경우(테스트 등)에만 결정론적 mock 검색 도구를 사용한다.
        request = AccommodationSearchRequest(
            destination=state.selected_destination,
            check_in=brief.start_date,
            check_out=brief.end_date,
            travelers=brief.travelers or 1,
            currency=state.currency,
            preference=brief.accommodation_preference,
        )
        state.accommodation_options = self.tool.search(request)
        return state
