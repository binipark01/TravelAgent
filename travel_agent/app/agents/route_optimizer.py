from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from math import ceil

from travel_agent.app.orchestration.state_machine import append_source_refs
from travel_agent.app.providers.base import RoutesProvider
from travel_agent.app.schemas.common import Location, Money
from travel_agent.app.schemas.itinerary import (
    DayPlan,
    FreeTimeBlock,
    Itinerary,
    ItineraryItem,
    MealSuggestion,
    TransferSegment,
)
from travel_agent.app.schemas.providers import POIOption, RouteMatrixRequest
from travel_agent.app.schemas.trip import TripPlanState
from travel_agent.app.utils.ids import new_id


class RouteAgent:
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
        ordered_pois = self._order_pois_by_area(state.poi_candidates)
        per_day = min(4, max(1, ceil(len(ordered_pois) / days_count))) if ordered_pois else 1
        chunks = [ordered_pois[i : i + per_day] for i in range(0, len(ordered_pois), per_day)]

        day_plans: list[DayPlan] = []
        for day_number in range(1, days_count + 1):
            pois = chunks[day_number - 1] if day_number - 1 < len(chunks) else []
            day_date = self._date_for_day(brief.start_date, day_number)
            day_plans.append(self._build_day(day_number, day_date, pois, state))

        itinerary = Itinerary(
            days=day_plans,
            summary=f"{state.selected_destination or 'Destination'} {days_count}일 mock itinerary",
            feasibility_flags=[],
        )
        for day in itinerary.days:
            if len(day.items) > 4:
                day.notes.append("하루 주요 일정이 4개를 초과합니다.")
                itinerary.feasibility_flags.append(f"day_{day.day}_overpacked")
            if day.day == 1:
                day.notes.append("도착일에는 공항 이동 및 체크인 버퍼를 확보했습니다.")
            if day.day == days_count:
                day.notes.append("출국일에는 공항 도착 2-3시간 전 버퍼가 필요합니다.")

        state.draft_itinerary = itinerary
        state.optimized_itinerary = itinerary
        return state

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
        self, day_number: int, day_date: date | None, pois: list[POIOption], state: TripPlanState
    ) -> DayPlan:
        area = pois[0].area if pois else None
        day = DayPlan(day=day_number, date=day_date, area=area)
        start_slots = [time(10, 0), time(14, 0), time(16, 30), time(19, 0)]
        for index, poi in enumerate(pois[:4]):
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
                    notes=poi.notes,
                    feasibility_flags=[],
                )
            )

        if day.items:
            self._add_transfers(day, [item.location for item in day.items], state)
        day.meals.extend(
            [
                MealSuggestion(
                    item_id=new_id("meal"),
                    meal_type="lunch",
                    title="지역 맛집 점심",
                    area=area or "Central",
                    start_time=time(12, 30),
                    end_time=time(13, 30),
                    estimated_cost=Money(amount=25_000, currency=state.currency),
                    notes=["식당 예약 가능 여부는 별도 확인이 필요합니다."],
                ),
                MealSuggestion(
                    item_id=new_id("meal"),
                    meal_type="dinner",
                    title="저녁 식사 및 휴식",
                    area=area or "Central",
                    start_time=time(18, 0),
                    end_time=time(19, 0),
                    estimated_cost=Money(amount=35_000, currency=state.currency),
                    notes=["식비는 mock 평균값입니다."],
                ),
            ]
        )
        day.free_time.append(
            FreeTimeBlock(
                item_id=new_id("free"),
                title="휴식/자유 시간",
                start_time=time(20, 30),
                end_time=time(21, 30),
                notes=["과밀 일정을 피하기 위한 여유 시간입니다."],
            )
        )
        return day

    def _add_transfers(self, day: DayPlan, locations: list[Location], state: TripPlanState) -> None:
        if len(locations) < 2:
            return
        legs = self.provider.compute_route_matrix(RouteMatrixRequest(locations=locations))
        append_source_refs(state, [leg.metadata.source_ref for leg in legs])
        for index, leg in enumerate(legs):
            start = day.items[index].end_time
            end = self._add_minutes(start, leg.travel_minutes)
            flags = ["long_transfer"] if leg.travel_minutes > 45 else []
            day.transfers.append(
                TransferSegment(
                    item_id=new_id("xfer"),
                    origin=leg.origin,
                    destination=leg.destination,
                    start_time=start,
                    end_time=end,
                    travel_minutes=leg.travel_minutes,
                    mode=leg.mode,
                    source_refs=[leg.metadata.source_ref.source_id],
                    feasibility_flags=flags,
                )
            )

    def _add_minutes(self, value: time, minutes: int) -> time:
        base = datetime.combine(date(2026, 1, 1), value)
        return (base + timedelta(minutes=minutes)).time()
