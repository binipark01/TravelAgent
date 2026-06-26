from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from math import ceil

from travel_agent.app.connectors.nearby.day_trips import lookup_nearby
from travel_agent.app.connectors.routes.local_transport import lookup_local_transport
from travel_agent.app.connectors.weather.open_meteo import (
    fetch_trip_daylight,
    fetch_trip_weather,
)
from travel_agent.app.llm.curator import (
    curate_city_pois,
    curate_companion_cities,
    curate_nearby,
    curate_stay_areas,
)
from travel_agent.app.llm.itinerary_arranger import (
    ArrangedDay,
    arrange_itinerary,
    curate_community_course,
)
from travel_agent.app.providers.base import RoutesProvider
from travel_agent.app.schemas.common import Location, Money
from travel_agent.app.schemas.itinerary import (
    DayPlan,
    Itinerary,
    ItineraryItem,
    MealSuggestion,
    TransferSegment,
)
from travel_agent.app.schemas.providers import POIOption
from travel_agent.app.schemas.trip import TripPlanState
from travel_agent.app.utils.ids import new_id

logger = logging.getLogger(__name__)

# 야경·전망(나이트뷰)이 아니면 그날 관광은 이 시각 안에 끝낸다(결정적 캡). 식사·숙소복귀·공항
# 이동은 캡 이후에도 정상 배치한다 — 섬·근교 막배 전 복귀 흐름이 자연스럽게 만들어진다.
_DAY_END_CAP = time(22, 0)
# 귀가(숙소/공항 복귀) 도착 상한 — 관광 자체는 22시 전에 끝나도 먼 근교는 귀가 이동이 자정까지
# 밀린다(사도·비에이 등). 그런 날은 뒤 곳수를 잘라 귀가가 이 시각을 넘지 않게 한다(critic도
# 23시 이후 종료를 '너무 늦음'으로 본다).
_HOME_RETURN_CAP = time(23, 0)
# 야경/전망류 판정 키워드(title 또는 매칭 POI.type). 이런 곳은 22시를 넘겨도 허용.
_NIGHT_VIEW_KEYWORDS = (
    "야경", "전망", "전망대", "전망실", "전망타워", "나이트", "night", "바", "bar",
    "선셋", "sunset", "일몰", "라이트업", "루프톱", "rooftop",
)
# 동선 anchor(공항·숙소/본거지/역) — 관광이 아니라 이동 출발/도착점이라 캡 대상이 아니다
# (캡이 걸려도 숙소 복귀·공항 이동 stop은 그대로 둬야 그날이 제대로 닫힌다).
_ANCHOR_KEYWORDS = ("공항", "空港", "airport", "숙소", "본거지", "호텔")


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

        # 날씨를 먼저 받아 표시에 재사용한다.
        weather = self._fetch_weather(state, brief, days_count)
        weather_by_day = self._weather_by_day(brief.start_date, days_count, weather)
        # 일출·일몰(실데이터/로컬계산)을 일차별로 받아 배치기에 넘긴다 — 야외 경치는 일몰 전,
        # 야경은 일몰 후에 배치하게 한다.
        daylight_by_day = self._daylight_by_day(state, brief, days_count)

        # 1순위: 디시·네이버카페·블로그의 '실제 다녀온 코스 후기'로 일정 구조를 가져온다.
        # 진짜 사람들의 동선이라 시간대(야경=밤)·숙소근처 시작이 자연스럽다. 못 찾으면(또는
        # 비활성) 아래 LLM 배치기로 폴백한다.
        arrangement = curate_community_course(
            state.selected_destination or "여행지",
            days_count=days_count,
            interests=brief.must_include,
            start_date=brief.start_date,
            daylight_by_day=daylight_by_day or None,
        )
        if arrangement is None:
            # 폴백: 근교·숙박구역·동반도시(병렬 프리페치) + LLM 배치기.
            self._prefetch_route_lookups(state.selected_destination, days_count)
            nearby_options = self._nearby_options(state.selected_destination)
            attractions, restaurants, companion_days = self._merge_companion_cities(
                state, days_count, attractions, restaurants
            )
            base_area = self._base_area(state.selected_destination)
            arrangement = arrange_itinerary(
                state.selected_destination or "여행지",
                days_count=days_count,
                attractions=attractions,
                restaurants=restaurants,
                pace=brief.pace,
                start_date=brief.start_date,
                weather_by_day=weather_by_day,
                nearby_options=nearby_options,
                companion_days=companion_days or None,
                base_area=base_area,
                daylight_by_day=daylight_by_day or None,
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

        self._apply_weather(itinerary, weather)
        # 공항↔본거지 이동에 정적 큐레이션 교통의 수단·운행간격을 결정적으로 반영(있을 때만).
        self._apply_airport_transfer_info(itinerary, state)
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
        # 식당은 보통 동선 근처라 도보 ~7분으로 잡아, 관광뿐 아니라 식사 앞에도 이동을 표시한다.
        meal_move = 7
        clock = time(10, 0)
        last_title: str | None = None
        # 직전 관광 → 다음 관광 이동(분, 수단). 식사를 건너뛰어도 보존했다가 다음 관광에 쓴다.
        pending: tuple[int, str] | None = None
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

        def add_transfer(
            origin: str, destination: str, start: time, minutes: int, mode: str
        ) -> time:
            end = self._add_minutes(start, minutes)
            day.transfers.append(
                TransferSegment(
                    item_id=new_id("xfer"),
                    origin=origin,
                    destination=destination,
                    start_time=start,
                    end_time=end,
                    travel_minutes=minutes,
                    mode=mode or "도보",
                )
            )
            return end

        def place_meal(meal_type: str, title: str, floor: time, cap: time) -> None:
            """식사의 '시작시간'만 창[floor, cap] 안에 유동적으로 둔다(끝은 창을 넘겨도 됨 —
            창 안에서 다 먹을 필요는 없다). 한 시각에 고정하지 않고 일정 흐름을 따르되, 너무
            이르면 floor, 너무 늦으면 cap으로 당긴다. 이동(도보)은 식당 도착 직전에 붙인다."""
            nonlocal clock, last_title
            earliest = self._add_minutes(clock, meal_move) if last_title is not None else clock
            start = min(max(earliest, floor), cap)
            if last_title is not None:
                t_start = self._add_minutes(start, -meal_move)
                if t_start < clock:
                    # 일정이 창을 넘겨 끝나 이동을 당겨 넣을 수 없으면 이동 직후로 둔다
                    # (시작이 창 끝을 살짝 넘겨도 OK).
                    t_start = clock
                    start = self._add_minutes(clock, meal_move)
                add_transfer(last_title, title, t_start, meal_move, "도보")
            meal_end = self._add_minutes(start, 60)
            add_meal(meal_type, title, start, meal_end)
            last_title, clock = title, meal_end

        # 식당으로 쓴 곳을 관광지로도 중복 배치하지 않는다(같은 카페가 점심+관광에 뜨는 버그).
        meal_titles = {t.strip().lower() for t in (arranged.lunch, arranged.dinner) if t}
        stops = [s for s in arranged.stops if s.title.strip().lower() not in meal_titles]
        # 그날 '귀가 이동'(마지막 정류장→숙소/공항)의 분·수단. 관광이 22시 전에 끝나도 먼 근교는
        # 귀가가 자정까지 밀리므로, 각 관광의 '귀가 도착 시각'을 투영해 캡 판정에 쓴다.
        return_leg, return_mode = 0, ""
        for idx in range(len(stops) - 1, 0, -1):
            if self._is_anchor_stop(stops[idx], None):
                return_leg = stops[idx - 1].travel_to_next_min
                return_mode = stops[idx - 1].travel_mode
                break
        # 결정적 캡: 비-야경 관광이 22시를 넘기거나(종료 기준), 22시 전에 끝나도 귀가 도착이 23시를
        # 넘기면(먼 근교) 그 stop부터 일반 관광은 더 안 놓는다. anchor(숙소 복귀·공항 이동)는 캡
        # 이후에도 놓아 그날을 제대로 닫는다.
        sightseeing_capped = False
        for stop in stops:
            poi = self._lookup(attr_by_title, stop.title)
            is_anchor = self._is_anchor_stop(stop, poi)
            is_night = self._is_night_view(stop, poi)
            # 점심(시작 11~14시)·저녁(시작 17~22시)을 동선 흐름에 끼운다. 식당 앞에도 이동을 넣고,
            # pending(직전 관광→다음 관광 이동)은 식사를 건너뛰어 보존했다 다음 관광에 쓴다.
            if not lunch_done and arranged.lunch and clock >= time(11, 30):
                place_meal("lunch", arranged.lunch, time(11, 0), time(14, 0))
                lunch_done = True
            if not dinner_done and arranged.dinner and clock >= time(17, 30):
                place_meal("dinner", arranged.dinner, time(18, 0), time(22, 0))
                dinner_done = True
            # 이미 캡이 걸렸으면 일반 관광은 건너뛴다(anchor 복귀/공항·야경류는 통과시킨다 —
            # 야경은 밤이라야 의미 있어 22시 넘겨도 허용).
            if sightseeing_capped and not is_anchor and not is_night:
                continue
            # 이 stop으로의 이동을 가정해 종료 시각을 미리 계산한다(아직 추가 전).
            if last_title is not None:
                if is_anchor and sightseeing_capped and return_leg:
                    # 캡으로 뒤쪽 관광을 잘랐으면 숙소 복귀는 '진짜 귀가 이동(마지막 정류장→숙소)'
                    # 시간으로 닫는다(중간 hop 이동을 귀가로 오용하지 않게).
                    minutes, mode = return_leg, return_mode or "대중교통"
                else:
                    minutes, mode = pending if pending else (meal_move, "도보")
            else:
                minutes, mode = 0, ""
            arrive = self._add_minutes(clock, minutes) if last_title is not None else clock
            end = self._add_minutes(arrive, stop.duration_min)
            # 캡: 비-야경·비-anchor 관광이 ① 22시를 넘겨 끝나거나 ② 22시 전에 끝나도 귀가 도착이
            # 23시를 넘기면(먼 근교) 캡을 걸고 이 stop을 버린다(이후 일반 관광도). 단 그날 첫 관광은
            # 귀가 기준으로는 안 자른다(최소 한 곳은 본다). _add_minutes는 자정을 넘기면 wrap(예:
            # 25:00→01:00)하므로 wrap도 '초과'로 본다.
            home_arrival = self._add_minutes(end, return_leg) if return_leg else end
            if not is_night and not is_anchor and (
                self._past_day_cap(end)
                or (last_title is not None and return_leg and self._past_home_cap(home_arrival))
            ):
                sightseeing_capped = True
                logger.info(
                    "일정 캡: %s일차 '%s'(종료 %s·귀가도착 %s) 제외(야경 아님)",
                    day_number, stop.title, end.strftime("%H:%M"),
                    home_arrival.strftime("%H:%M"),
                )
                continue  # pending은 보존 → 다음에 놓이는 stop(보통 anchor 복귀)이 이 이동을 쓴다
            # 실제 배치: 이동 추가 후 stop 추가.
            if last_title is not None:
                clock = add_transfer(last_title, stop.title, clock, minutes, mode)
                pending = None
            end = self._add_minutes(clock, stop.duration_min)
            day.items.append(self._arranged_item(stop, poi, clock, end, currency, state))
            last_title, clock = stop.title, end
            pending = (
                (stop.travel_to_next_min, stop.travel_mode)
                if stop.travel_to_next_min > 0
                else None
            )

        # 흐름상 못 넣은 식사 보강(시작시간만 창 안, 끝은 넘겨도 됨). 점심은 자연스러운 정오쯤,
        # 저녁은 자연스러운 저녁때(18시)부터 — 일정이 늦게 끝나면 그 흐름을 따라간다.
        if not lunch_done and arranged.lunch:
            place_meal("lunch", arranged.lunch, time(12, 0), time(14, 0))
        if not dinner_done and arranged.dinner:
            place_meal("dinner", arranged.dinner, time(18, 0), time(22, 0))
        return day

    @staticmethod
    def _past_day_cap(end: time) -> bool:
        """종료 시각이 하루 캡(22:00)을 넘겼는지. 일정은 10시에 시작하므로 자정을 넘겨 wrap된
        시각(00:00~09:59)도 '초과'로 본다(_add_minutes가 25:00→01:00처럼 wrap하기 때문).
        """
        return end > _DAY_END_CAP or end < time(10, 0)

    @staticmethod
    def _past_home_cap(arrival: time) -> bool:
        """귀가(숙소/공항 복귀) 도착이 너무 늦은지(23시 이후, 또는 자정 wrap). 관광 자체는 22시
        전에 끝나도 먼 근교는 귀가가 자정까지 밀리므로, 이걸로 그런 날의 뒤 곳수를 잘라낸다."""
        return arrival > _HOME_RETURN_CAP or arrival < time(10, 0)

    @staticmethod
    def _is_night_view(stop, poi: POIOption | None) -> bool:
        """야경·전망(나이트뷰)류인지 — title 키워드 또는 매칭 POI.type 키워드로 판정.

        이런 곳만 22시 캡을 넘겨 늦게까지 허용한다(야경은 밤이라야 의미 있으니).
        """
        text = (stop.title or "").lower()
        if poi:
            text += " " + (poi.type or "").lower()
        return any(k in text for k in _NIGHT_VIEW_KEYWORDS)

    @staticmethod
    def _is_anchor_stop(stop, poi: POIOption | None) -> bool:
        """동선 anchor(공항·숙소/본거지/역)인지 — 이동 출발/도착점이라 캡 대상이 아니다."""
        text = (stop.title or "").lower()
        if poi:
            text += " " + (poi.type or "").lower()
        return any(k in text for k in _ANCHOR_KEYWORDS)

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
        # 풀에서 못 찾으면(드묾) 최소 정보로 만든다. 공항(첫날 도착·마지막날 출국)은 '공항',
        # 매일 출발점인 본거지(숙소 부근/역)는 '숙소'로 표시한다(관광지로 오인 방지).
        is_airport = any(k in stop.title for k in ("공항", "空港", "airport", "Airport"))
        is_base = "숙소" in stop.title or "본거지" in stop.title
        stop_type = "공항" if is_airport else "숙소" if is_base else "관광지"
        return ItineraryItem(
            item_id=new_id("item"),
            title=stop.title,
            type=stop_type,
            location=Location(name=state.selected_destination or stop.title, area=None),
            start_time=start,
            end_time=end,
            estimated_cost=Money(amount=0, currency=currency),
            booking_required=False,
            source_refs=[],
            notes=[],
            feasibility_flags=[],
        )

    @staticmethod
    def _nearby_options(destination: str | None) -> list[str]:
        """근교 당일치기 후보 이름 목록(있으면). curate_nearby가 캐시되어 NearbyAgent와 공유."""
        if not destination:
            return []
        guide = curate_nearby(destination) or lookup_nearby(destination)
        if not guide:
            return []
        return [dest.name for dest in guide.destinations][:6]

    @staticmethod
    def _prefetch_route_lookups(destination: str | None, days_count: int) -> None:
        """일정 생성 직전에 필요한 독립 웹검색(근교·숙박구역·동반도시 판단)을 동시에 돌려
        캐시를 데운다. 직렬 합산(~2~3분) → 가장 느린 하나(~30~60초)로 단축. 실패는 무시
        (본 호출에서 폴백)."""
        if not destination:
            return
        tasks = (
            lambda: curate_nearby(destination),
            lambda: curate_stay_areas(destination),
            lambda: curate_companion_cities(destination, days_count),
        )
        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            futures = [executor.submit(task) for task in tasks]
            for future in futures:
                try:
                    future.result()
                except Exception as exc:  # noqa: BLE001 - 사전 조회 실패는 본 호출에서 폴백
                    # 동작은 불변(본 호출에서 폴백), 왜 프리페치가 실패했는지만 남긴다.
                    logger.info(
                        "근교/숙박구역/동반도시 프리페치 실패 dest=%s reason=%s",
                        destination, exc,
                    )

    @staticmethod
    def _base_area(destination: str | None) -> str | None:
        """일정의 기준점 = 추천 숙박 구역 1순위(도시 메인 부근). curate_stay_areas는 캐시되어
        StayAreaAgent와 결과를 공유하므로(웹검색 1회), 일정과 숙박 추천이 같은 구역을 본다."""
        if not destination:
            return None
        guide = curate_stay_areas(destination)
        if guide and guide.areas:
            return guide.areas[0].name
        return None

    def _merge_companion_cities(
        self,
        state: TripPlanState,
        days_count: int,
        attractions: list[POIOption],
        restaurants: list[POIOption],
    ) -> tuple[list[POIOption], list[POIOption], dict[str, int]]:
        """오사카↔교토처럼 사실상 같이 가는 핵심 도시의 실제 명소를 풀에 합치고, 도시별
        일수를 돌려준다. 비활성/짧은 일정/없음이면 입력 그대로(단일 도시)."""
        destination = state.selected_destination
        brief = state.brief
        if not destination or brief is None:
            return attractions, restaurants, {}
        companions = curate_companion_cities(destination, days_count)
        if not companions:
            return attractions, restaurants, {}
        # 본거지가 일정의 과반이 되게 동반 도시 일수 합을 제한(4일→1, 7일→2, 10일→3).
        budget = max(1, (days_count - 1) // 3)
        city_days: dict[str, int] = {}
        for comp in companions:
            if budget <= 0:
                break
            give = min(max(comp.days, 1), budget)
            pois = curate_city_pois(
                comp.city,
                interests=brief.must_include,
                start_date=brief.start_date,
                currency=state.currency,
                attraction_pool=[],
                restaurant_pool=[],
            )
            if not pois or not (pois.attractions or pois.restaurants):
                continue
            attractions = attractions + [self._tag_city(p, comp.city) for p in pois.attractions]
            restaurants = restaurants + [self._tag_city(p, comp.city) for p in pois.restaurants]
            city_days[comp.city] = give
            budget -= give
        return attractions, restaurants, city_days

    @staticmethod
    def _tag_city(poi: POIOption, city: str) -> POIOption:
        """배치기가 도시별로 묶도록 area 앞에 도시명을 붙인다('교토 · 기온')."""
        area = (poi.area or "").strip()
        if area.startswith(city):
            new_area = area
        elif area:
            new_area = f"{city} · {area}"
        else:
            new_area = city
        return poi.model_copy(update={"area": new_area})

    def _fetch_weather(self, state, brief, days_count: int) -> dict[date, str]:
        """여행 날짜별 날씨를 한 번 받아 dict로 돌려준다(실패하면 빈 dict)."""
        if not state.selected_destination or not brief.start_date:
            return {}
        end = brief.end_date or (brief.start_date + timedelta(days=days_count - 1))
        try:
            return fetch_trip_weather(state.selected_destination, brief.start_date, end)
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _weather_by_day(
        start_date: date | None, days_count: int, weather: dict[date, str]
    ) -> dict[int, str]:
        """날짜별 날씨를 '일차 번호 → 라벨'로 바꿔 배치기에 넘긴다."""
        if not start_date or not weather:
            return {}
        result: dict[int, str] = {}
        for day_number in range(1, days_count + 1):
            day_date = start_date + timedelta(days=day_number - 1)
            if day_date in weather:
                result[day_number] = weather[day_date]
        return result

    def _daylight_by_day(
        self, state, brief, days_count: int
    ) -> dict[int, tuple[time, time]]:
        """일차별 (일출, 일몰) 현지시각. 지오코딩/네트워크 실패해도 로컬 계산으로 채워진다.

        실패(목적지·날짜 없음)면 빈 dict → 배치기는 일조 블록을 생략한다(폴백).
        """
        if not state.selected_destination or not brief.start_date:
            return {}
        end = brief.end_date or (brief.start_date + timedelta(days=days_count - 1))
        try:
            daylight = fetch_trip_daylight(state.selected_destination, brief.start_date, end)
        except (OSError, ValueError):
            return {}
        result: dict[int, tuple[time, time]] = {}
        for day_number in range(1, days_count + 1):
            day_date = brief.start_date + timedelta(days=day_number - 1)
            if day_date in daylight:
                result[day_number] = daylight[day_date]
        return result

    @staticmethod
    def _apply_weather(itinerary, weather: dict[date, str]) -> None:
        """여행 날짜별 날씨를 일정 각 날짜에 붙인다(표시용)."""
        for day in itinerary.days:
            if day.date and day.date in weather:
                day.weather = weather[day.date]

    # 공항 이동 매칭 키워드(origin/destination에 있으면 공항 이동으로 본다).
    _AIRPORT_KEYWORDS = ("공항", "空港", "airport")

    def _apply_airport_transfer_info(self, itinerary, state: TripPlanState) -> None:
        """첫날 도착(공항→본거지)·마지막날 출국(본거지→공항) 이동에 정적 큐레이션 교통의
        수단명·운행간격을 결정적으로 붙인다. 외부 fetch 없음(정적 순수함수). 매칭되는 교통이
        없거나 운행정보가 없으면 기존 mode를 그대로 둔다(폴백). 특정 출발시각은 만들지 않는다.
        """
        destination = state.primary_destination
        if not destination:
            return
        plan = lookup_local_transport(destination)
        if plan is None or not plan.airport_transfers:
            return
        # 운행간격(frequency)이 있는 교통만 후보로(빈칸은 안 붙인다). 가장 잘 맞는 하나를 고른다.
        rail = [t for t in plan.airport_transfers if t.frequency]
        if not rail:
            return
        for day in itinerary.days:
            for transfer in day.transfers:
                if not self._is_airport_transfer(transfer):
                    continue
                match = self._match_airport_transit(transfer, rail)
                if match is None:
                    continue
                transfer.mode = self._enrich_mode(transfer.mode, transfer.travel_minutes, match)

    def _is_airport_transfer(self, transfer) -> bool:  # noqa: ANN001 - TransferSegment
        text = f"{transfer.origin} {transfer.destination}".lower()
        return any(k in text for k in self._AIRPORT_KEYWORDS)

    @staticmethod
    def _match_airport_transit(transfer, rail: list):  # noqa: ANN001 - TransferSegment 등
        """transfer의 mode 텍스트와 겹치는 교통수단을 우선 매칭(이름의 토큰 부분일치).
        못 맞추면 첫 후보(대표 철도 노선)로 폴백 — 도시당 대표 공항철도가 가장 흔하다."""
        mode_text = (transfer.mode or "").lower()
        for item in rail:
            # 노선명 토큰(괄호·공백 분리) 중 하나라도 mode에 들어 있으면 매칭.
            tokens = [
                tok
                for tok in item.name.replace("(", " ").replace(")", " ").split()
                if len(tok) >= 2
            ]
            if any(tok.lower() in mode_text for tok in tokens):
                return item
        return rail[0]

    @staticmethod
    def _enrich_mode(mode: str, travel_minutes: int, item) -> str:  # noqa: ANN001 - LocalTransportItem
        """mode 텍스트에 '수단명 · 운행간격'을 덧붙인다(이미 들어있으면 중복 추가 안 함).
        예: '전철' → '난카이 라피트(특급) · 약 30분 간격'. 특정 출발시각은 만들지 않는다."""
        freq = item.frequency
        # 이미 운행간격 정보가 붙어 있으면(재실행 등) 중복 방지.
        if freq and freq in (mode or ""):
            return mode
        # 수단명이 mode에 없으면 수단명을 앞세우고, 있으면 mode를 유지한 채 간격만 덧붙인다.
        base = mode if (mode and item.name.split("(")[0].strip() in mode) else item.name
        return f"{base} · {freq}" if freq else base

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
