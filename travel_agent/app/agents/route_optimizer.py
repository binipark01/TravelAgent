from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from math import ceil

from travel_agent.app.connectors.weather.open_meteo import fetch_trip_weather
from travel_agent.app.providers.base import RoutesProvider
from travel_agent.app.schemas.common import Money
from travel_agent.app.schemas.itinerary import (
    DayPlan,
    FreeTimeBlock,
    Itinerary,
    ItineraryItem,
    MealSuggestion,
)
from travel_agent.app.schemas.providers import POIOption
from travel_agent.app.schemas.trip import TripPlanState
from travel_agent.app.utils.ids import new_id


class RouteAgent:
    """실데이터(관광지 + 맛집)로 날짜별 추천 일정을 만든다.

    관광지(activity_options)를 날짜별 방문 일정으로 배치하고, 맛집(poi_candidates)을
    점심/저녁으로 분배한다. 장소가 없으면 일정도 비운다(mock 미사용).
    """

    def __init__(self, provider: RoutesProvider) -> None:
        self.provider = provider

    def run(self, state: TripPlanState) -> TripPlanState:
        brief = state.brief
        if not brief:
            return state
        days_count = brief.duration_days or (
            (brief.end_date - brief.start_date).days + 1
            if brief.start_date and brief.end_date
            else 1
        )
        days_count = max(days_count, 1)

        attractions = state.activity_options or state.poi_candidates
        ordered = self._order_pois_by_area(attractions)
        per_day = min(3, max(1, ceil(len(ordered) / days_count))) if ordered else 0
        chunks = (
            [ordered[i : i + per_day] for i in range(0, len(ordered), per_day)] if per_day else []
        )
        restaurants = state.poi_candidates

        day_plans: list[DayPlan] = []
        for day_number in range(1, days_count + 1):
            pois = chunks[day_number - 1] if day_number - 1 < len(chunks) else []
            day_date = self._date_for_day(brief.start_date, day_number)
            day_plans.append(self._build_day(day_number, day_date, pois, restaurants, state))

        itinerary = Itinerary(
            days=day_plans,
            summary=f"{state.selected_destination or '여행지'} {days_count}일 추천 일정",
            feasibility_flags=[],
        )
        for day in itinerary.days:
            if day.day == 1:
                day.notes.append("도착일 — 공항 이동·체크인 버퍼를 두세요.")
            if day.day == days_count and days_count > 1:
                day.notes.append("출국일 — 공항 도착 2-3시간 전 버퍼가 필요합니다.")

        self._attach_weather(itinerary, state, brief, days_count)
        state.draft_itinerary = itinerary
        state.optimized_itinerary = itinerary
        return state

    def _attach_weather(self, itinerary, state, brief, days_count: int) -> None:
        """여행 날짜별 날씨를 일정 각 날짜에 붙인다(실패해도 일정은 그대로)."""
        if not state.selected_destination or not brief.start_date:
            return
        end = brief.end_date or (brief.start_date + timedelta(days=days_count - 1))
        try:
            weather = fetch_trip_weather(state.selected_destination, brief.start_date, end)
        except (OSError, ValueError):
            return
        for day in itinerary.days:
            if day.date and day.date in weather:
                day.weather = weather[day.date]

    def _order_pois_by_area(self, pois: list[POIOption]) -> list[POIOption]:
        grouped: dict[str, list[POIOption]] = defaultdict(list)
        for poi in pois:
            grouped[poi.area or "General"].append(poi)
        ordered: list[POIOption] = []
        for area in sorted(grouped):
            ordered.extend(grouped[area])
        return ordered

    def _date_for_day(self, start_date: date | None, day_number: int) -> date | None:
        return start_date + timedelta(days=day_number - 1) if start_date else None

    def _build_day(
        self,
        day_number: int,
        day_date: date | None,
        pois: list[POIOption],
        restaurants: list[POIOption],
        state: TripPlanState,
    ) -> DayPlan:
        area = pois[0].area if pois else None
        day = DayPlan(day=day_number, date=day_date, area=area)
        start_slots = [time(10, 0), time(14, 0), time(16, 30)]
        for index, poi in enumerate(pois[:3]):
            start_time = start_slots[index]
            end_time = self._add_minutes(start_time, min(poi.recommended_duration_minutes, 120))
            day.items.append(
                ItineraryItem(
                    item_id=new_id("item"),
                    title=poi.title,
                    type=poi.type,
                    location=poi.location,
                    start_time=start_time,
                    end_time=end_time,
                    estimated_cost=poi.estimated_cost,
                    booking_required=poi.booking_required,
                    source_refs=[poi.metadata.source_ref.source_id],
                    notes=poi.notes[:1],
                    feasibility_flags=[],
                )
            )
        day.meals.extend(self._meals_for_day(day_number - 1, restaurants, state.currency))
        day.free_time.append(
            FreeTimeBlock(
                item_id=new_id("free"),
                title="자유 시간",
                start_time=time(20, 30),
                end_time=time(21, 30),
                notes=["과밀 일정을 피하기 위한 여유 시간입니다."],
            )
        )
        return day

    def _meals_for_day(
        self, day_index: int, restaurants: list[POIOption], currency: str
    ) -> list[MealSuggestion]:
        if not restaurants:
            return []
        meals: list[MealSuggestion] = []
        slots = [("lunch", time(12, 30), time(13, 30)), ("dinner", time(18, 30), time(19, 30))]
        for meal_index, (meal_type, start_time, end_time) in enumerate(slots):
            restaurant = restaurants[(day_index * 2 + meal_index) % len(restaurants)]
            rating_note = next((note for note in restaurant.notes if "평점" in note), None)
            meals.append(
                MealSuggestion(
                    item_id=new_id("meal"),
                    meal_type=meal_type,
                    title=restaurant.title,
                    area=restaurant.type or "",
                    start_time=start_time,
                    end_time=end_time,
                    estimated_cost=Money(amount=0, currency=currency),
                    source_refs=[restaurant.metadata.source_ref.source_id],
                    notes=[rating_note] if rating_note else [],
                )
            )
        return meals

    def _add_minutes(self, value: time, minutes: int) -> time:
        base = datetime.combine(date(2026, 1, 1), value)
        return (base + timedelta(minutes=minutes)).time()
