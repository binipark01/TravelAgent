"""첫날 도착공항·마지막날 출국공항이 일정에 들어가는지 검증하는 개발 프로브.

1순위 경로(curate_community_course)를 도시별로 돌려, day1 첫 stop과 마지막 날 마지막
stop이 공항인지 확인한다. 커뮤니티 코스를 못 찾으면(None) arrange_itinerary로 폴백.

사용: python scripts/airport_itinerary_probe.py
"""

from __future__ import annotations

from datetime import date

from travel_agent.app.llm.itinerary_arranger import (
    ArrangedItinerary,
    arrange_itinerary,
    curate_community_course,
)
from travel_agent.app.llm.curator import curate_city_pois

CITIES = [("오사카", 4), ("파리", 5), ("방콕", 4)]


def _is_airport(title: str) -> bool:
    return any(k in title for k in ("공항", "空港", "airport", "Airport"))


def _build(city: str, days: int) -> tuple[str, ArrangedItinerary | None]:
    course = curate_community_course(
        city, days_count=days, interests=None, start_date=date(2026, 7, 1)
    )
    if course is not None:
        return "community", course
    pois = curate_city_pois(
        city,
        interests=None,
        start_date=date(2026, 7, 1),
        currency="KRW",
        attraction_pool=[],
        restaurant_pool=[],
    )
    if not pois:
        return "none", None
    course = arrange_itinerary(
        city,
        days_count=days,
        attractions=pois.attractions,
        restaurants=pois.restaurants,
        pace=None,
        start_date=date(2026, 7, 1),
    )
    return "arrange", course


def main() -> None:
    for city, days in CITIES:
        source, course = _build(city, days)
        print(f"\n===== {city} {days}일 (source={source}) =====", flush=True)
        if not course:
            print("  (일정 생성 실패)", flush=True)
            continue
        for d in course.days:
            first = d.stops[0].title if d.stops else "(빈 날)"
            last = d.stops[-1].title if d.stops else "(빈 날)"
            flags = []
            if d.day == 1 and _is_airport(first):
                flags.append("✅도착공항")
            elif d.day == 1:
                flags.append("❌첫날 공항없음")
            if d.day == len(course.days) and _is_airport(last):
                flags.append("✅출국공항")
            elif d.day == len(course.days):
                flags.append("❌마지막날 공항없음")
            tag = ("  " + " ".join(flags)) if flags else ""
            print(f"  Day{d.day} [{d.area}]: 첫={first} / 끝={last}{tag}", flush=True)


if __name__ == "__main__":
    main()
