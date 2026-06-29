from __future__ import annotations

from travel_agent.app.connectors.visa.entry_requirements import (
    lookup_entry_requirements,
    resolve_country,
)
from travel_agent.app.schemas.trip import TripPlanState

# 한국인 여행자 기준 '국내'로 보는 목적지 국가 — 비자(국제 입국 요건) 카드를 띄우지 않는다.
_HOME_COUNTRIES = {"대한민국", "한국", "korea", "south korea"}
# resolve_country가 LLM 비활성(오프라인)이면 한국 도시를 못 풀어 None을 주므로, 흔한 국내
# 도시명도 결정적으로 본다(부분일치). 국내 도시는 좁은 집합이라 오탐 위험이 낮다.
_DOMESTIC_KEYWORDS = (
    "제주", "부산", "서울", "인천", "대구", "광주", "대전", "울산", "강릉", "경주",
    "여수", "속초", "전주", "포항", "춘천", "통영", "가평", "양양",
)


class VisaAgent:
    """목적지+국적 기준 입국 요건(무비자 기간·전자여행허가·여권 유효기간)을 채운다.

    국내 여행(제주·부산 등)은 국제 입국 요건이 없으므로 비자 카드를 생략한다.
    """

    def run(self, state: TripPlanState) -> TripPlanState:
        brief = state.brief
        destination = state.primary_destination
        if not destination:
            return state
        country = resolve_country(destination)
        is_domestic = (
            (country and country.strip().lower() in _HOME_COUNTRIES)
            or any(k in destination for k in _DOMESTIC_KEYWORDS)
        )
        if is_domestic:
            state.visa_result = None  # 국내 여행 — 비자 불필요
            return state
        passport = brief.passport_country if brief else None
        start = brief.start_date if brief else None
        end = brief.end_date if brief else None
        state.visa_result = lookup_entry_requirements(destination, passport, start, end)
        return state
