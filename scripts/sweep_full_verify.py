"""메인도시 25곳 전체 파이프라인 전수 검증 — 일정 + 모든 카드 내용.

multicity_quality_probe(일정 차원)와 달리, 실제 앱과 같은 전체 run_planning을 돌려
optimized_itinerary뿐 아니라 비자·환율·항공·숙소·POI추천·근교·숙박구역·교통권·예산·
체크리스트까지 모든 카드 '내용'을 도시별 기대값(국가·통화·공항)과 대조한다.

점검:
 [일정] 22시/귀가 캡(late), 일몰 정합, 시장오전·박물관마감, 공항 북엔드, 과밀.
 [내용] visa.destination_country=기대국가? fx.target_currency=기대통화? 항공 도착=기대공항?
        교통권 hub_lat/lng 존재(지도 지오코딩 bias 전제)? POI non-mock·출처? 근교/숙박/
        교통/예산/체크리스트 존재·산출?

per-city JSON을 scratchpad/sweep_full/에 쓰며 resume-skip. 콘솔은 ASCII 요약만.
사용: python -m scripts.sweep_full_verify
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta

import scripts.multicity_quality_probe as P
from travel_agent.app.agents.supervisor import TravelSupervisorAgent
from travel_agent.app.config import get_settings
from travel_agent.app.orchestration.run_context import build_run_context
from travel_agent.app.schemas.trip import TripPlanState
from travel_agent.app.utils.ids import new_id

OUT_DIR = P.OUT_DIR + r"\sweep_full"
START = date(2026, 7, 10)

# (지역, 도시, 일수, (국가KR, 국가EN), 통화, 공항코드들)
CITIES = [
    ("EU", "런던", 5, ("영국", "United Kingdom"), "GBP", ["LHR", "LGW", "Heathrow"]),
    ("EU", "파리", 5, ("프랑스", "France"), "EUR", ["CDG", "ORY", "Charles"]),
    ("EU", "로마", 5, ("이탈리아", "Italy"), "EUR", ["FCO", "Fiumicino", "Rome"]),
    ("EU", "바르셀로나", 4, ("스페인", "Spain"), "EUR", ["BCN", "Barcelona", "Prat"]),
    ("EU", "암스테르담", 4, ("네덜란드", "Netherlands"), "EUR", ["AMS", "Schiphol"]),
    ("EU", "프라하", 4, ("체코", "Czech"), "CZK", ["PRG", "Prague", "Václav"]),
    ("EU", "비엔나", 4, ("오스트리아", "Austria"), "EUR", ["VIE", "Vienna", "Schwechat"]),
    ("EU", "베를린", 4, ("독일", "Germany"), "EUR", ["BER", "Berlin", "Brandenburg"]),
    ("EU", "리스본", 4, ("포르투갈", "Portugal"), "EUR", ["LIS", "Lisbon", "Lisboa"]),
    ("EU", "취리히", 4, ("스위스", "Switzerland"), "CHF", ["ZRH", "Zurich", "Zürich"]),
    ("AS", "도쿄", 5, ("일본", "Japan"), "JPY", ["HND", "NRT", "Haneda", "Narita"]),
    ("AS", "오사카", 4, ("일본", "Japan"), "JPY", ["KIX", "Kansai", "ITM"]),
    ("AS", "방콕", 4, ("태국", "Thailand"), "THB", ["BKK", "DMK", "Suvarnabhumi"]),
    ("AS", "싱가포르", 4, ("싱가포르", "Singapore"), "SGD", ["SIN", "Changi"]),
    ("AS", "홍콩", 4, ("홍콩", "Hong Kong"), "HKD", ["HKG", "Hong Kong", "Chek Lap"]),
    ("AS", "타이베이", 4, ("대만", "Taiwan"), "TWD", ["TPE", "Taoyuan", "Taipei"]),
    ("AS", "하노이", 4, ("베트남", "Vietnam"), "VND", ["HAN", "Hanoi", "Noi Bai"]),
    ("AS", "쿠알라룸푸르", 4, ("말레이시아", "Malaysia"), "MYR", ["KUL", "Kuala Lumpur"]),
    ("AS", "다낭", 4, ("베트남", "Vietnam"), "VND", ["DAD", "Da Nang", "Danang"]),
    ("AS", "세부", 4, ("필리핀", "Philippines"), "PHP", ["CEB", "Cebu", "Mactan"]),
    ("US", "뉴욕", 5, ("미국", "United States"), "USD", ["JFK", "EWR", "LGA", "New York"]),
    ("US", "로스앤젤레스", 4, ("미국", "United States"), "USD", ["LAX", "Los Angeles"]),
    ("US", "라스베이거스", 4, ("미국", "United States"), "USD", ["LAS", "Las Vegas", "Harry Reid"]),
    ("US", "샌프란시스코", 4, ("미국", "United States"), "USD", ["SFO", "San Francisco"]),
    ("US", "호놀룰루", 4, ("미국", "United States"), "USD", ["HNL", "Honolulu", "Daniel"]),
]


def _txt(v: object) -> str:
    return (str(v) if v is not None else "").lower()


def _matches_any(haystack: str, needles: list) -> bool:
    low = haystack.lower()
    return any(n.lower() in low for n in needles)


def _content_checks(st: TripPlanState, country, currency, airports) -> dict:
    """모든 카드 내용 점검 → {present:{}, issues:[]}."""
    issues: list[str] = []
    country_needles = list(country)

    # 비자: 목적지 국가 일치
    visa = st.visa_result
    if not visa:
        issues.append("비자없음")
    else:
        c = _txt(visa.destination_country)
        if c and not _matches_any(c, country_needles):
            issues.append(f"비자국가불일치:{visa.destination_country}!={country[0]}")

    # 환율: 대상 통화 일치
    fx = st.fx_info
    if not fx:
        issues.append("환율없음")
    else:
        if currency.lower() not in _txt(fx.target_currency):
            issues.append(f"환율통화불일치:{fx.target_currency}!={currency}")
        if not (fx.target_per_base and fx.target_per_base > 0):
            issues.append("환율율0")

    # 항공: 비-mock 1건+ & 도착 공항/도시 일치
    flights = [
        f for f in (st.transport_options or [])
        if not getattr(getattr(f, "metadata", None), "is_mock", False)
    ]
    if not flights:
        issues.append("항공0건(non-mock)")
    else:
        dests = " ".join(_txt(f.destination) for f in flights)
        if not _matches_any(dests, airports):
            issues.append(f"항공도착불일치:{flights[0].destination}")

    # 교통권: hub 좌표(지도 지오코딩 bias 전제) + 국가
    tk = st.transport_tickets
    if not tk:
        issues.append("교통권없음")
    else:
        if tk.hub_lat is None or tk.hub_lng is None:
            issues.append("교통권hub좌표없음")
        if tk.destination_country and not _matches_any(
            _txt(tk.destination_country), country_needles
        ):
            issues.append(f"교통권국가불일치:{tk.destination_country}")

    # POI: 비-mock 추천 수 & 출처
    pois = list(st.poi_candidates or []) + list(st.activity_options or [])
    nonmock = [
        p for p in pois
        if not getattr(getattr(getattr(p, "metadata", None), "source_ref", None), "is_mock", True)
    ]
    if len(nonmock) < 4:
        issues.append(f"POI추천부족:{len(nonmock)}(non-mock)")

    # 나머지 카드 존재
    if not st.nearby_guide or not st.nearby_guide.destinations:
        issues.append("근교없음")
    if not st.stay_area_guide or not st.stay_area_guide.areas:
        issues.append("숙박구역없음")
    if not st.local_transport:
        issues.append("현지교통없음")
    if not (st.budget and st.budget.total_estimated_cost and st.budget.total_estimated_cost > 0):
        issues.append("예산0")
    if not st.prep_checklist or not st.prep_checklist.groups:
        issues.append("체크리스트없음")

    present = {
        "visa": bool(visa),
        "fx": bool(fx),
        "flights_nonmock": len(flights),
        "tickets_hub_coords": bool(tk and tk.hub_lat is not None and tk.hub_lng is not None),
        "poi_nonmock": len(nonmock),
        "nearby": bool(st.nearby_guide and st.nearby_guide.destinations),
        "stay_areas": bool(st.stay_area_guide and st.stay_area_guide.areas),
        "local_transport": bool(st.local_transport),
        "budget_total": getattr(st.budget, "total_estimated_cost", None) if st.budget else None,
        "checklist": bool(st.prep_checklist and st.prep_checklist.groups),
    }
    return {"present": present, "content_issues": issues}


def run_city_full(sup, region, city, days, country, currency, airports) -> dict:
    st = TripPlanState(
        trip_id=new_id("trip"), currency="KRW", raw_user_message=P._brief_text(city, days)
    )
    # 실제 앱(백그라운드 run)과 같은 전체 워크플로우 — stay_area·checklist·events·multicity까지
    # 코어플래너가 동적 선택해 돈다(run_planning은 그 일부만 도는 축약 경로).
    sup.run_agent_workflow(st)
    it = st.optimized_itinerary
    if not it or not it.days:
        return {"region": region, "city": city, "days": days, "error": "일정 생성 실패"}

    # 일정 차원(일몰 포함) — multicity_quality_probe 재사용.
    sunset_by_day: dict[int, object] = {}
    try:
        from travel_agent.app.connectors.weather.open_meteo import fetch_trip_daylight
        end = START + timedelta(days=days - 1)
        dl = fetch_trip_daylight(city, START, end)
        for i in range(days):
            d = START + timedelta(days=i)
            if d in dl:
                sunset_by_day[i + 1] = dl[d][1]
    except Exception:  # noqa: BLE001
        pass
    days_out = [P._analyze_day(d, sunset_by_day.get(d.day)) for d in it.days]
    sched_issues = [iss for d in days_out for iss in d["issues"]]
    late_flags = [f for f in (it.feasibility_flags or []) if "너무 늦" in f]
    first_items = it.days[0].items
    last_items = it.days[-1].items
    last_label = last_items[-1].title if last_items else ""

    # 항공 도착은 공항코드 대신 도시명('도쿄')으로 저장되기도 하니 도시명도 매칭에 포함.
    content = _content_checks(st, country, currency, [*airports, city])
    return {
        "region": region,
        "city": city,
        "days": days,
        "sched_issue_count": len(sched_issues),
        "sched_issues": sched_issues,
        "late_finish": len(late_flags),
        "late_flags": late_flags,
        "overcrowd": len([f for f in (st.critic_findings or []) if "과밀" in f.message]),
        "air_bookends": [
            bool(first_items) and P._has(first_items[0].title, P.AIRPORT),
            P._has(last_label, P.AIRPORT),
        ],
        "content_issue_count": len(content["content_issues"]),
        "content_issues": content["content_issues"],
        "present": content["present"],
        "days_detail": days_out,
    }


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    sup = TravelSupervisorAgent(build_run_context(get_settings()))
    rollup = []
    for region, city, days, country, currency, airports in CITIES:
        path = f"{OUT_DIR}\\city_{city}.json"
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    cached = json.load(fh)
                if not cached.get("error"):
                    print(f"[skip] {region} {city}", flush=True)
                    rollup.append(_roll(cached))
                    continue
            except Exception:  # noqa: BLE001
                pass
        print(f"[run ] {region} {city} {days}d ...", flush=True)
        try:
            r = run_city_full(sup, region, city, days, country, currency, airports)
        except Exception as exc:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            r = {"region": region, "city": city, "days": days, "error": repr(exc)}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(r, fh, ensure_ascii=False, indent=2, default=str)
        print(
            f"    -> sched={r.get('sched_issue_count','E')} late={r.get('late_finish','E')} "
            f"overcrowd={r.get('overcrowd','E')} content={r.get('content_issue_count','E')} "
            f"air={r.get('air_bookends')} err={r.get('error')}",
            flush=True,
        )
        rollup.append(_roll(r))
    with open(f"{OUT_DIR}\\_rollup.json", "w", encoding="utf-8") as fh:
        json.dump(rollup, fh, ensure_ascii=False, indent=2, default=str)
    print("\n===== ROLLUP (details in sweep_full/_rollup.json) =====", flush=True)
    print(json.dumps(rollup, ensure_ascii=True, indent=2, default=str), flush=True)


def _roll(r: dict) -> dict:
    return {
        "region": r.get("region"), "city": r.get("city"), "days": r.get("days"),
        "late_finish": r.get("late_finish"), "overcrowd": r.get("overcrowd"),
        "sched_issues": r.get("sched_issues", []),
        "content_issues": r.get("content_issues", []),
        "air_bookends": r.get("air_bookends"), "present": r.get("present"),
        "error": r.get("error"),
    }


if __name__ == "__main__":
    main()
