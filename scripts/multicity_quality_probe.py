"""다도시 일정 품질 전수 검증 프로브.

사용자 지적(① 1시까지 가는 일정 ② 깜깜할 때 경치 ③ 밤에 어시장)이 다른 도시에서도
없는지 확인한다. 도시별로 실제 앱과 같은 전체 파이프라인(run_planning)을 in-process로
돌려 optimized_itinerary를 만들고, 다음을 점검해 JSON으로 저장한다:

  · 마무리시간: 야경/anchor 아닌 마지막 관광 종료 ≤ 22:00 (캡 동작)
  · 일몰 정합: 실 일몰(Open-Meteo/로컬계산) 이후에 '주간 경치/전망/공원/해변' 배치 여부
  · 업종시간: 시장류 시작<15:00, 박물관류 종료≤17:30
  · 북엔드: 1일차 첫 stop=공항? 마지막날 마지막=공항/숙소?
  · critic feasibility_flags

결과는 scratchpad에 city별 JSON + 요약을 남긴다. (LLM 켜져 있어야 의미 있음)

사용: python scripts/multicity_quality_probe.py
"""

from __future__ import annotations

import json
import sys
from datetime import date, time, timedelta

import travel_agent.app.agent_core.runtime  # noqa: F401  # 순환 임포트 회피(먼저 로드)
from travel_agent.app.agents.supervisor import TravelSupervisorAgent
from travel_agent.app.config import get_settings
from travel_agent.app.connectors.weather.open_meteo import fetch_trip_daylight
from travel_agent.app.orchestration.run_context import build_run_context
from travel_agent.app.schemas.trip import TripPlanState
from travel_agent.app.utils.ids import new_id

OUT_DIR = (
    r"C:\Users\PSB\AppData\Local\Temp\claude"
    r"\D--Agents-TravelAgent--claude-worktrees-frosty-meninsky-9a006c"
    r"\42618451-be15-41f8-ad83-bb730ab3b826\scratchpad"
)

START = date(2026, 7, 10)

# (도시, 일수, 자연어 브리프) — intake가 brief를 채우게 한다(실제 사용자 입력처럼).
CITIES = [
    ("도쿄", 5),
    ("후쿠오카", 4),
    ("삿포로", 4),
    ("방콕", 4),
    ("파리", 5),
]

SCENIC = ("경치", "전망", "공원", "해변", "산책", "정원", "뷰", "view", "park", "garden")
NIGHTVIEW = ("야경", "나이트", "라이트업", "night", "일몰", "선셋", "sunset")
MARKET = ("시장", "어시장", "수산", "청과", "market")
MUSEUM = ("박물관", "미술관", "전시", "museum", "gallery")
AIRPORT = ("공항", "空港", "airport")


def _brief_text(city: str, days: int) -> str:
    end = START + timedelta(days=days - 1)
    return (
        f"인천에서 {city} {days}일 여행 가려고 해. {START.isoformat()}부터 {end.isoformat()}까지, "
        f"성인 2명, 예산 200만원, 무난한 페이스로 관광지랑 맛집 위주로 추천해줘. 여권은 한국."
    )


def _t(value) -> str:
    return value.strftime("%H:%M") if isinstance(value, time) else "?"


def _has(text: str, words) -> bool:
    low = (text or "").lower()
    return any(w.lower() in low for w in words)


def _analyze_day(day, sunset: time | None) -> dict:
    items = list(day.items)
    issues: list[str] = []
    # 마무리: 야경/공항/숙소 아닌 마지막 관광 종료시간
    last_sight_end: time | None = None
    for it in items:
        is_nightish = _has(it.title, NIGHTVIEW) or _has(it.type or "", NIGHTVIEW)
        is_anchor = _has(it.title, AIRPORT) or (it.type in ("공항", "숙소"))
        if not is_nightish and not is_anchor:
            last_sight_end = it.end_time
    if last_sight_end and (last_sight_end > time(22, 0) or last_sight_end < time(8, 0)):
        issues.append(f"늦은마무리:{_t(last_sight_end)}")
    # 일몰 후 주간경치
    if sunset:
        for it in items:
            if _has(it.title, SCENIC) and not _has(it.title, NIGHTVIEW):
                if it.start_time and it.start_time > sunset:
                    issues.append(f"일몰후경치:{it.title}({_t(it.start_time)}>일몰{_t(sunset)})")
    # 시장 늦은 시작
    for it in items:
        if _has(it.title, MARKET) or _has(it.type or "", MARKET):
            if it.start_time and it.start_time >= time(15, 0):
                issues.append(f"시장늦음:{it.title}({_t(it.start_time)})")
    # 박물관 늦은 종료
    for it in items:
        if _has(it.title, MUSEUM) or _has(it.type or "", MUSEUM):
            if it.end_time and it.end_time > time(17, 30):
                issues.append(f"박물관늦음:{it.title}({_t(it.end_time)})")
    return {
        "day": day.day,
        "area": day.area,
        "sunset": _t(sunset) if sunset else None,
        "items": [
            {
                "t": f"{_t(it.start_time)}~{_t(it.end_time)}",
                "title": it.title,
                "type": it.type,
            }
            for it in items
        ],
        "last_sight_end": _t(last_sight_end) if last_sight_end else None,
        "issues": issues,
    }


def run_city(supervisor, city: str, days: int) -> dict:
    state = TripPlanState(
        trip_id=new_id("trip"),
        currency="KRW",
        raw_user_message=_brief_text(city, days),
    )
    supervisor.run_planning(state)
    it = state.optimized_itinerary
    if not it or not it.days:
        return {"city": city, "days": days, "error": "일정 생성 실패", "itinerary": None}

    # 실 일몰(일차→sunset)
    sunset_by_day: dict[int, time] = {}
    try:
        end = START + timedelta(days=days - 1)
        dl = fetch_trip_daylight(city, START, end)
        for i in range(days):
            d = START + timedelta(days=i)
            if d in dl:
                sunset_by_day[i + 1] = dl[d][1]
    except Exception as exc:  # noqa: BLE001 - 프로브, 실패해도 계속
        print(f"  [{city}] 일몰 fetch 실패: {exc}", file=sys.stderr, flush=True)

    days_out = [_analyze_day(d, sunset_by_day.get(d.day)) for d in it.days]
    # 북엔드
    first_items = it.days[0].items if it.days else []
    last_day_items = it.days[-1].items if it.days else []
    first_is_airport = bool(first_items) and _has(first_items[0].title, AIRPORT)
    last_label = last_day_items[-1].title if last_day_items else ""
    last_is_airport = _has(last_label, AIRPORT)

    all_issues = [iss for d in days_out for iss in d["issues"]]
    return {
        "city": city,
        "days": days,
        "summary": it.summary,
        "feasibility_flags": list(it.feasibility_flags or []),
        "critic_findings": [
            {"severity": f.severity.value, "message": f.message}
            for f in (state.critic_findings or [])
        ],
        "bookends": {
            "day1_first": first_items[0].title if first_items else None,
            "day1_first_is_airport": first_is_airport,
            "lastday_last": last_label or None,
            "lastday_last_is_airport": last_is_airport,
        },
        "issue_count": len(all_issues),
        "issues": all_issues,
        "days_detail": days_out,
    }


def main() -> None:
    settings = get_settings()
    supervisor = TravelSupervisorAgent(build_run_context(settings))
    rollup = []
    for city, days in CITIES:
        print(f"\n===== {city} {days}일 생성 중… =====", flush=True)
        try:
            result = run_city(supervisor, city, days)
        except Exception as exc:  # noqa: BLE001 - 프로브
            import traceback

            traceback.print_exc()
            result = {"city": city, "days": days, "error": repr(exc)}
        path = f"{OUT_DIR}\\city_{city}.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2, default=str)
        issue_n = result.get("issue_count", "ERR")
        flags = len(result.get("feasibility_flags", []) or [])
        be = result.get("bookends", {}) or {}
        print(
            f"  → 이슈 {issue_n}개 · feasibility_flags {flags}개 · "
            f"day1공항={be.get('day1_first_is_airport')} "
            f"막날공항={be.get('lastday_last_is_airport')}",
            flush=True,
        )
        rollup.append(
            {
                "city": city,
                "days": days,
                "issue_count": issue_n,
                "feasibility_flags": result.get("feasibility_flags", []),
                "bookends": be,
                "issues": result.get("issues", []),
                "error": result.get("error"),
            }
        )
    with open(f"{OUT_DIR}\\_rollup.json", "w", encoding="utf-8") as fh:
        json.dump(rollup, fh, ensure_ascii=False, indent=2, default=str)
    # 콘솔(cp949)에서 한글/한자 인코딩으로 죽지 않게 ASCII-안전하게 요약만 찍는다.
    # 상세는 _rollup.json / city_*.json(utf-8)에 있다.
    print("\n===== ROLLUP (상세는 _rollup.json) =====", flush=True)
    print(json.dumps(rollup, ensure_ascii=True, indent=2, default=str), flush=True)


if __name__ == "__main__":
    main()
