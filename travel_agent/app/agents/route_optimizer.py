from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from math import ceil

from travel_agent.app.connectors.weather.open_meteo import fetch_trip_weather
from travel_agent.app.llm.itinerary_arranger import ArrangedDay, arrange_itinerary
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

        # 대화형 수정: '빼줘/제외'(must_avoid)·'넣어줘'(must_include)·페이스를 반영한다.
        # 매 턴이 새 run이라도 이 제약들은 history로 누적돼 일정에 계속 적용된다.
        attractions = self._apply_edits(state.activity_options or state.poi_candidates, brief)
        restaurants = self._apply_edits(state.poi_candidates, brief)

        # LLM이 지리적 근접성으로 동선을 배치하면(이동시간 포함) 그걸 쓰고, 비활성/실패 시
        # 기존 휴리스틱(area 묶음 + 고정 시간표)으로 폴백한다.
        arrangement = arrange_itinerary(
            state.selected_destination or "여행지",
            days_count=days_count,
            attractions=attractions,
            restaurants=restaurants,
            pace=brief.pace,
            start_date=brief.start_date,
        )
        if arrangement:
            day_plans = self._build_days_from_arrangement(
                arrangement, attractions, restaurants, brief, days_count, state
            )
        else:
            day_plans = self._build_days_heuristic(
                attractions, restaurants, brief, days_count, state
            )

        itinerary = Itinerary(
            days=day_plans,
            summary=f"{state.selected_destination or '여행지'} {days_count}일 추천 일정",
            feasibility_flags=[],
        )
        for day in itinerary.days:
            if day.day == 1:
                day.notes.append("도착일 — 공항→숙소 이동·체크인 시간 버퍼를 넉넉히 두세요.")
            if day.day == days_count and days_count > 1:
                day.notes.append(
                    "출국일 — 비행기 출발 2~3시간 전까지 공항에 도착하세요"
                    "(국제선 체크인·보안검색 여유)."
                )

        self._attach_weather(itinerary, state, brief, days_count)
        state.draft_itinerary = itinerary
        state.optimized_itinerary = itinerary
        return state

    def _build_days_heuristic(
        self,
        attractions: list[POIOption],
        restaurants: list[POIOption],
        brief,
        days_count: int,
        state: TripPlanState,
    ) -> list[DayPlan]:
        """기존 휴리스틱: area 묶음 + 고정 시간표(LLM 배치 비활성/실패 시 폴백)."""
        ordered = self._order_pois_by_area(attractions)
        per_day = self._per_day(brief, ordered, days_count)
        chunks = (
            [ordered[i : i + per_day] for i in range(0, len(ordered), per_day)] if per_day else []
        )
        day_plans: list[DayPlan] = []
        for day_number in range(1, days_count + 1):
            pois = chunks[day_number - 1] if day_number - 1 < len(chunks) else []
            day_date = self._date_for_day(brief.start_date, day_number)
            day_plans.append(self._build_day(day_number, day_date, pois, restaurants, state))
        return day_plans

    def _build_days_from_arrangement(
        self,
        arrangement,
        attractions: list[POIOption],
        restaurants: list[POIOption],
        brief,
        days_count: int,
        state: TripPlanState,
    ) -> list[DayPlan]:
        """LLM이 짠 동선(순서·이동시간)으로 날짜별 일정을 만든다."""
        attr_by_title = self._index_by_title(attractions)
        rest_by_title = self._index_by_title(restaurants)
        day_plans: list[DayPlan] = []
        for day_number, arranged in enumerate(arrangement.days[:days_count], start=1):
            day_date = self._date_for_day(brief.start_date, day_number)
            day_plans.append(
                self._build_arranged_day(
                    day_number, day_date, arranged, attr_by_title, rest_by_title, state
                )
            )
        # 배치가 날 수보다 적으면 남는 날은 빈 일정으로 채운다.
        for day_number in range(len(day_plans) + 1, days_count + 1):
            day_plans.append(
                DayPlan(day=day_number, date=self._date_for_day(brief.start_date, day_number))
            )
        return day_plans

    @staticmethod
    def _index_by_title(pois: list[POIOption]) -> dict[str, POIOption]:
        return {poi.title.strip().lower(): poi for poi in pois}

    @staticmethod
    def _lookup(index: dict[str, POIOption], title: str) -> POIOption | None:
        key = title.strip().lower()
        if key in index:
            return index[key]
        for stored_key, poi in index.items():
            if key and (key in stored_key or stored_key in key):
                return poi
        return None

    def _build_arranged_day(
        self,
        day_number: int,
        day_date,
        arranged: ArrangedDay,
        attr_by_title: dict[str, POIOption],
        rest_by_title: dict[str, POIOption],
        state: TripPlanState,
    ) -> DayPlan:
        day = DayPlan(day=day_number, date=day_date, area=arranged.area)
        if arranged.note:
            day.notes.append(arranged.note)
        currency = state.currency
        clock = time(10, 0)
        lunch_done = False
        dinner_done = False

        def add_meal(meal_type: str, title: str, start: time, end: time) -> None:
            poi = self._lookup(rest_by_title, title)
            notes: list[str] = []
            source_refs: list[str] = []
            area = ""
            if poi:
                why = next((n for n in poi.notes if n.startswith("💡") or "평점" in n), None)
                if why:
                    notes = [why]
                source_refs = [poi.metadata.source_ref.source_id]
                area = poi.type or ""
            day.meals.append(
                MealSuggestion(
                    item_id=new_id("meal"),
                    meal_type=meal_type,
                    title=poi.title if poi else title,
                    area=area,
                    start_time=start,
                    end_time=end,
                    estimated_cost=Money(amount=0, currency=currency),
                    source_refs=source_refs,
                    notes=notes,
                )
            )

        stops = arranged.stops
        for index, stop in enumerate(stops):
            # 점심·저녁을 동선 흐름 속에 끼워넣는다(시각이 지나면 다음 방문 전에 삽입).
            if not lunch_done and arranged.lunch and clock >= time(12, 0):
                end = self._add_minutes(clock, 60)
                add_meal("lunch", arranged.lunch, clock, end)
                clock = end
                lunch_done = True
            if not dinner_done and arranged.dinner and clock >= time(17, 30):
                end = self._add_minutes(clock, 60)
                add_meal("dinner", arranged.dinner, clock, end)
                clock = end
                dinner_done = True
            poi = self._lookup(attr_by_title, stop.title)
            end = self._add_minutes(clock, stop.duration_min)
            day.items.append(self._arranged_item(stop, poi, clock, end, currency, state))
            clock = end
            if stop.travel_to_next_min > 0 and index < len(stops) - 1:
                transfer_end = self._add_minutes(clock, stop.travel_to_next_min)
                day.transfers.append(
                    TransferSegment(
                        item_id=new_id("xfer"),
                        origin=stop.title,
                        destination=stops[index + 1].title,
                        start_time=clock,
                        end_time=transfer_end,
                        travel_minutes=stop.travel_to_next_min,
                        mode=stop.travel_mode,
                    )
                )
                clock = transfer_end

        # 흐름상 못 넣은 식사는 표준 시각으로 보강한다.
        if not lunch_done and arranged.lunch:
            add_meal("lunch", arranged.lunch, time(12, 30), time(13, 30))
        if not dinner_done and arranged.dinner:
            add_meal("dinner", arranged.dinner, time(18, 30), time(19, 30))

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

    def _arranged_item(
        self,
        stop,
        poi: POIOption | None,
        start: time,
        end: time,
        currency: str,
        state: TripPlanState,
    ) -> ItineraryItem:
        if poi:
            return ItineraryItem(
                item_id=new_id("item"),
                title=poi.title,
                type=poi.type,
                location=poi.location,
                start_time=start,
                end_time=end,
                estimated_cost=poi.estimated_cost,
                booking_required=poi.booking_required,
                source_refs=[poi.metadata.source_ref.source_id],
                notes=poi.notes[:1],
                feasibility_flags=[],
            )
        # 풀에서 못 찾으면(드묾) 최소 정보로 만든다.
        return ItineraryItem(
            item_id=new_id("item"),
            title=stop.title,
            type="관광지",
            location=Location(name=state.selected_destination or stop.title, area=None),
            start_time=start,
            end_time=end,
            estimated_cost=Money(amount=0, currency=currency),
            booking_required=False,
            source_refs=[],
            notes=[],
            feasibility_flags=[],
        )

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

    def _apply_edits(self, pois: list[POIOption], brief) -> list[POIOption]:
        """대화형 수정 반영: must_avoid는 제외, must_include는 앞으로 올린다(부분일치)."""
        avoid = [
            token.strip().lower()
            for token in (brief.must_avoid or [])
            if token and token.strip().lower() not in ("overpacked days",)
        ]
        if avoid:
            pois = [
                poi
                for poi in pois
                if not any(
                    token in poi.title.lower() or token in (poi.type or "").lower()
                    for token in avoid
                )
            ]
        include = [token.strip().lower() for token in (brief.must_include or []) if token.strip()]
        if include:
            pois = sorted(
                pois,
                key=lambda poi: 0
                if any(
                    token in poi.title.lower() or token in (poi.type or "").lower()
                    for token in include
                )
                else 1,
            )
        return pois

    def _per_day(self, brief, ordered: list[POIOption], days_count: int) -> int:
        """페이스에 따라 하루 방문지 수를 정한다. 여유=적게, 빡빡=많이."""
        if not ordered:
            return 0
        base = min(3, max(1, ceil(len(ordered) / days_count)))
        if brief.pace == "relaxed":
            return max(1, min(base, 2))
        if brief.pace == "packed":
            return min(4, base + 1)
        return base

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
        start_slots = [time(10, 0), time(13, 30), time(15, 30), time(17, 0)]
        for index, poi in enumerate(pois[: len(start_slots)]):
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
