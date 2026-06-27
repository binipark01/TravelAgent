"""메인도시 25곳(유럽10·아시아10·미국5) 일정 품질 경량 전수 스윕.

일정 품질(22시·귀가 캡·일몰정합·시장오전·박물관마감·공항 북엔드)은 실제 일정엔진인
route_agent(community-course LLM + 결정적 캡 + 일몰) + critic만 타면 충실히 검증된다.
항공/숙소/비자/예산 등은 일정 '시각'에 영향이 없어 제외(도시당 ~1 LLM콜로 경량화).

per-city JSON을 scratchpad/sweep25/에 쓰며, 이미 있고 error 없으면 건너뛴다(resume).
콘솔은 cp949 안전하게 ASCII 요약만 찍는다(상세는 JSON).

사용: python scripts/sweep_cities_light.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta

import scripts.multicity_quality_probe as P
import travel_agent.app.agent_core.runtime  # noqa: F401  # 순환 임포트 회피(먼저 로드)
from travel_agent.app.agents.supervisor import TravelSupervisorAgent
from travel_agent.app.config import get_settings
from travel_agent.app.connectors.weather.open_meteo import fetch_trip_daylight
from travel_agent.app.orchestration.run_context import build_run_context
from travel_agent.app.schemas.brief import TripBrief
from travel_agent.app.schemas.trip import TripPlanState
from travel_agent.app.utils.ids import new_id

OUT_DIR = P.OUT_DIR + r"\sweep25"
START = date(2026, 7, 10)

# (지역, 도시, 일수) — 각 지역 메인도시.
CITIES = [
    ("EU", "런던", 5), ("EU", "파리", 5), ("EU", "로마", 5), ("EU", "바르셀로나", 4),
    ("EU", "암스테르담", 4), ("EU", "프라하", 4), ("EU", "비엔나", 4), ("EU", "베를린", 4),
    ("EU", "리스본", 4), ("EU", "취리히", 4),
    ("AS", "도쿄", 5), ("AS", "오사카", 4), ("AS", "방콕", 4), ("AS", "싱가포르", 4),
    ("AS", "홍콩", 4), ("AS", "타이베이", 4), ("AS", "하노이", 4), ("AS", "쿠알라룸푸르", 4),
    ("AS", "다낭", 4), ("AS", "세부", 4),
    ("US", "뉴욕", 5), ("US", "로스앤젤레스", 4), ("US", "라스베이거스", 4),
    ("US", "샌프란시스코", 4), ("US", "호놀룰루", 4),
]


def run_city_light(sup: TravelSupervisorAgent, city: str, days: int) -> dict:
    st = TripPlanState(
        trip_id=new_id("trip"), currency="KRW", raw_user_message=f"{city} {days}일 여행"
    )
    end = START + timedelta(days=days - 1)
    st.brief = TripBrief(
        selected_destination=city,
        destinations=[city],
        start_date=START,
        end_date=end,
        duration_days=days,
    )
    st.selected_destination = city
    sup.route_agent.run(st)
    sup.critic_agent.run(st)
    it = st.optimized_itinerary
    if not it or not it.days:
        return {"city": city, "days": days, "error": "일정 생성 실패"}

    sunset_by_day: dict[int, object] = {}
    try:
        dl = fetch_trip_daylight(city, START, end)
        for i in range(days):
            d = START + timedelta(days=i)
            if d in dl:
                sunset_by_day[i + 1] = dl[d][1]
    except Exception as exc:  # noqa: BLE001 - 프로브
        print(f"  [{city}] sunset fetch fail: {exc!r}", file=sys.stderr, flush=True)

    days_out = [P._analyze_day(d, sunset_by_day.get(d.day)) for d in it.days]
    first_items = it.days[0].items
    last_items = it.days[-1].items
    last_label = last_items[-1].title if last_items else ""
    all_issues = [iss for d in days_out for iss in d["issues"]]
    late_flags = [f for f in (it.feasibility_flags or []) if "너무 늦" in f or "23" in f]
    return {
        "city": city,
        "days": days,
        "feasibility_flags": list(it.feasibility_flags or []),
        "late_finish_flags": late_flags,
        "overcrowd_findings": [
            f.message for f in (st.critic_findings or []) if "과밀" in f.message
        ],
        "bookends": {
            "day1_first": first_items[0].title if first_items else None,
            "day1_first_is_airport": bool(first_items) and P._has(first_items[0].title, P.AIRPORT),
            "lastday_last": last_label or None,
            "lastday_last_is_airport": P._has(last_label, P.AIRPORT),
        },
        "issue_count": len(all_issues),
        "issues": all_issues,
        "days_detail": days_out,
    }


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    settings = get_settings()
    sup = TravelSupervisorAgent(build_run_context(settings))
    rollup = []
    for region, city, days in CITIES:
        path = f"{OUT_DIR}\\city_{city}.json"
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    cached = json.load(fh)
                if not cached.get("error"):
                    print(f"[skip] {region} {city} (cached)", flush=True)
                    rollup.append({"region": region, **_roll(cached)})
                    continue
            except Exception:  # noqa: BLE001
                pass
        print(f"[run ] {region} {city} {days}d ...", flush=True)
        try:
            result = run_city_light(sup, city, days)
        except Exception as exc:  # noqa: BLE001 - 프로브
            import traceback

            traceback.print_exc()
            result = {"city": city, "days": days, "error": repr(exc)}
        result["region"] = region
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2, default=str)
        be = result.get("bookends", {}) or {}
        print(
            f"    -> issues={result.get('issue_count', 'ERR')} "
            f"late={len(result.get('late_finish_flags', []) or [])} "
            f"overcrowd={len(result.get('overcrowd_findings', []) or [])} "
            f"bookend_air={be.get('day1_first_is_airport')}/{be.get('lastday_last_is_airport')} "
            f"err={result.get('error')}",
            flush=True,
        )
        rollup.append({"region": region, **_roll(result)})
    with open(f"{OUT_DIR}\\_rollup.json", "w", encoding="utf-8") as fh:
        json.dump(rollup, fh, ensure_ascii=False, indent=2, default=str)
    print("\n===== ROLLUP (details in sweep25/_rollup.json) =====", flush=True)
    print(json.dumps(rollup, ensure_ascii=True, indent=2, default=str), flush=True)


def _roll(r: dict) -> dict:
    be = r.get("bookends", {}) or {}
    return {
        "city": r.get("city"),
        "days": r.get("days"),
        "issue_count": r.get("issue_count"),
        "late_finish": len(r.get("late_finish_flags", []) or []),
        "overcrowd": len(r.get("overcrowd_findings", []) or []),
        "air_bookends": [be.get("day1_first_is_airport"), be.get("lastday_last_is_airport")],
        "issues": r.get("issues", []),
        "error": r.get("error"),
    }


if __name__ == "__main__":
    main()
