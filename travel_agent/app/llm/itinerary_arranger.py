"""LLM(Codex)으로 하루 동선을 '실제 흐름'으로 배치하는 일정 배치기.

기존 RouteAgent는 관광지를 area 알파벳순으로 묶어 고정 시간표(10:00·13:30·…)에 채워
이동시간·동선을 무시했다. 여기서는 LLM이 지리적 근접성으로 관광지를 날짜에 배분하고,
하루 안에서 되돌아가지 않게 순서를 잡고, 연속 방문지 사이 대략 이동시간·교통수단을
추정한다. 식당도 그날 동선 근처로 점심/저녁에 배치한다.

웹검색까진 필요 없어 일반 Codex 추론으로 부른다(빠름). 라이브 LLM이 꺼져 있거나 실패하면
None을 돌려주어 RouteAgent가 기존 휴리스틱으로 폴백한다(오프라인 테스트 영향 없음).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from travel_agent.app.agents.llm_client import codex_brief_available, run_codex_json
from travel_agent.app.config import get_settings
from travel_agent.app.schemas.providers import POIOption


@dataclass(frozen=True)
class ArrangedStop:
    title: str
    duration_min: int
    travel_to_next_min: int  # 다음 방문지까지 이동(분). 마지막이면 0.
    travel_mode: str  # 도보/버스/지하철/택시 등


@dataclass(frozen=True)
class ArrangedDay:
    day: int
    area: str | None
    note: str | None
    stops: list[ArrangedStop]
    lunch: str | None
    dinner: str | None


@dataclass(frozen=True)
class ArrangedItinerary:
    days: list[ArrangedDay] = field(default_factory=list)


def _enabled() -> bool:
    settings = get_settings()
    return settings.enable_live_llm and codex_brief_available(settings.codex_cli_command)


def _pool_block(pool: list[POIOption], limit: int) -> str:
    lines = []
    for poi in pool[:limit]:
        area = f" [{poi.area}]" if poi.area else ""
        dur = poi.recommended_duration_minutes or 90
        lines.append(f"- {poi.title}{area} (~{dur}분)")
    return "\n".join(lines) if lines else "(없음)"


def _coerce_int(value: object, default: int, *, low: int, high: int) -> int:
    try:
        result = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(low, min(result, high))


def _weather_block(weather_by_day: dict[int, str] | None) -> str:
    if not weather_by_day:
        return ""
    lines = "\n".join(f"  - {day}일차: {label}" for day, label in sorted(weather_by_day.items()))
    return (
        "\n날짜별 날씨 예보(아래)를 반영하라. 비/눈/흐림 예보인 날엔 실내 위주(미술관·박물관·"
        "수족관·쇼핑몰·온천), 맑은 날엔 야외 위주(공원·전망대·해변·산책)로 배치하라.\n"
        f"{lines}\n"
    )


def arrange_itinerary(
    destination: str,
    *,
    days_count: int,
    attractions: list[POIOption],
    restaurants: list[POIOption],
    pace: str | None,
    start_date: date | None,
    weather_by_day: dict[int, str] | None = None,
) -> ArrangedItinerary | None:
    """관광지·식당을 날짜별 동선으로 배치한다. 비활성/실패 시 None."""
    if not _enabled() or days_count < 1 or not attractions:
        return None
    settings = get_settings()

    pace_hint = {
        "relaxed": "하루 2~3곳으로 여유롭게",
        "packed": "하루 4곳까지 알차게",
    }.get(pace or "", "하루 3곳 안팎으로")
    season = f" 여행 시기는 {start_date.year}년 {start_date.month}월경." if start_date else ""

    prompt = (
        f"너는 '{destination}' {days_count}일 여행의 동선을 짜는 한국어 플래너다. "
        "아래 관광지·식당 목록만 사용해, 같은 날에는 지리적으로 가까운 곳끼리 묶어 "
        "되돌아가지 않는 순서로 배치하라. 연속 방문지 사이의 대략 이동시간(분)과 교통수단을 "
        "추정하고, 점심·저녁 식당은 그날 동선 근처로 고른다. "
        f"페이스는 {pace_hint}.{season} "
        "목록에 없는 장소는 쓰지 마라. 가까운 area끼리 같은 날에 모은다.\n"
        f"{_weather_block(weather_by_day)}\n"
        f"[관광지]\n{_pool_block(attractions, 14)}\n\n"
        f"[식당]\n{_pool_block(restaurants, 12)}\n\n"
        "출력은 설명·코드펜스 없이 아래 JSON 객체 하나만:\n"
        "{\n"
        '  "days": [\n'
        '    {"day":1, "area":"그날 중심 지역", "note":"그날 동선 한줄 설명",\n'
        '     "stops":[{"title":"정확한 관광지명", "duration_min":90, '
        '"travel_to_next_min":15, "travel_mode":"도보/버스/지하철/택시"}],\n'
        '     "lunch":"식당명 또는 null", "dinner":"식당명 또는 null"}\n'
        "  ]\n"
        "}\n"
        "마지막 stop의 travel_to_next_min은 0. 모든 관광지를 한 번씩만, 날 수에 맞게 분배."
    )
    data = run_codex_json(
        prompt,
        command=settings.codex_cli_command,
        model=settings.codex_oauth_model,
        reasoning_effort=settings.codex_reasoning_effort,
        timeout_seconds=min(settings.codex_oauth_timeout_seconds, 120),
    )
    if not isinstance(data, dict):
        return None
    raw_days = data.get("days")
    if not isinstance(raw_days, list) or not raw_days:
        return None

    days: list[ArrangedDay] = []
    for index, raw in enumerate(raw_days, start=1):
        if not isinstance(raw, dict):
            continue
        raw_stops = raw.get("stops")
        if not isinstance(raw_stops, list):
            continue
        stops: list[ArrangedStop] = []
        for raw_stop in raw_stops:
            if not isinstance(raw_stop, dict):
                continue
            title = raw_stop.get("title")
            if not isinstance(title, str) or not title.strip():
                continue
            stops.append(
                ArrangedStop(
                    title=title.strip(),
                    duration_min=_coerce_int(
                        raw_stop.get("duration_min"), 90, low=30, high=240
                    ),
                    travel_to_next_min=_coerce_int(
                        raw_stop.get("travel_to_next_min"), 0, low=0, high=240
                    ),
                    travel_mode=(raw_stop.get("travel_mode") or "이동").strip() or "이동",
                )
            )
        if not stops:
            continue
        days.append(
            ArrangedDay(
                day=_coerce_int(raw.get("day"), index, low=1, high=days_count),
                area=(raw.get("area") or "").strip() or None,
                note=(raw.get("note") or "").strip() or None,
                stops=stops,
                lunch=(raw.get("lunch") or "").strip() or None,
                dinner=(raw.get("dinner") or "").strip() or None,
            )
        )
    if not days:
        return None
    return ArrangedItinerary(days=days)
