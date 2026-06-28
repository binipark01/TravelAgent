from __future__ import annotations

from travel_agent.app.llm.curator import recommend_destinations
from travel_agent.app.schemas.trip import TripPlanState

# 의도조차 없을 때의 최후 기본값(한글). hint가 있으면 LLM 추천이 우선한다.
_LAST_RESORT = "오사카"
# 도시가 아니라 '국가/지역'이라 그대로 거점으로 쓰면 안 되는 값들(LLM 추천으로 구체화).
_VAGUE_PLACES = {"일본", "japan", "한국", "korea", "유럽", "동남아", "미국", "usa"}


class DestinationDiscoveryAgent:
    """목적지 후보를 정한다. 사용자가 도시를 콕 집었으면 그대로, 분위기·테마·지역만 말했으면
    (예: '일본 온천', '따뜻한 휴양지', '유럽') destination_hint로 LLM이 실제 도시를 추천한다.
    """

    def run(self, state: TripPlanState) -> TripPlanState:
        brief = state.brief
        if brief is None:
            return state
        cities = [d for d in (brief.destinations or []) if d and d.strip()]
        vague = not cities or all(c.strip().lower() in _VAGUE_PLACES for c in cities)

        if vague and state.selected_destination is None:
            hint = (brief.destination_hint or "").strip() or (cities[0] if cities else "")
            rec = recommend_destinations(hint, brief.must_include) if hint else None
            # LLM 추천이 있으면 그 도시들, 없으면(LLM 비활성/실패) 국가·지역명을 그대로 거점으로
            # 쓰지 않고 최후 기본 도시로 떨어뜨린다('일본'·'유럽'을 거점으로 두면 안 됨).
            cities = list(rec) if rec else [_LAST_RESORT]
            brief.destinations = list(cities)

        if not cities:
            cities = [_LAST_RESORT]
        state.destination_candidates = cities
        if state.selected_destination is None:
            food_or_shopping = {"food", "shopping"} & set(brief.must_include)
            state.selected_destination = (
                "오사카" if ("오사카" in cities or "Osaka" in cities) and food_or_shopping
                else cities[0]
            )
        return state
