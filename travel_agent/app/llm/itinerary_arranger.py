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


def _multicity_block(base_city: str, companion_days: dict[str, int] | None) -> str:
    """동반 도시(예: 오사카의 교토)를 별도의 날로 묶어 배치하게 하는 지시."""
    if not companion_days:
        return ""
    parts = ", ".join(f"{city} {days}일" for city, days in companion_days.items())
    cities = " / ".join(companion_days.keys())
    return (
        f"\n이 일정은 여러 도시로 구성된다. 도시별 권장 일수: {base_city}는 나머지 전부, "
        f"{parts}.\n"
        f"[관광지]·[식당]에서 area가 '{cities}'로 시작하는 곳은 그 도시이고, 그 외는 "
        f"{base_city}다. 각 도시는 연속된 날(들)로 묶어 그 도시 장소만 그 날에 배치하라"
        "(한 하루 안에서 도시를 섞지 마라). 도시가 바뀌는 날은 note 맨 앞에 "
        "'○○에서 △△로 이동(전철/기차 약 N분)'을 적고, 그 날 area를 '△△ · 동네'로 하라. "
        f"본거지 {base_city}는 첫날과 마지막날을 포함하도록 배치하라.\n"
    )


def _nearby_block(nearby_options: list[str] | None) -> str:
    if not nearby_options:
        return ""
    names = ", ".join(nearby_options[:6])
    return (
        f"\n근교 당일치기 후보: {names}.\n"
        "일정이 여유로우면(페이스가 여유롭거나 날 수에 비해 시내 명소가 넉넉하지 않으면) "
        "하루를 근교 당일치기로 배정해도 좋다. 그 날은 stops에 근교 1곳을 넣고 area를 "
        "'근교: 도시명'으로, duration_min을 크게(300~480) 줘라. 빡빡하면 근교는 넣지 말고 "
        "시내만 채워라.\n"
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
    nearby_options: list[str] | None = None,
    companion_days: dict[str, int] | None = None,
) -> ArrangedItinerary | None:
    """관광지·식당을 날짜별 동선으로 배치한다. 비활성/실패 시 None."""
    if not _enabled() or days_count < 1 or not attractions:
        return None
    settings = get_settings()

    pace_hint = {
        "relaxed": "하루 3~4곳으로 여유롭게",
        "packed": "하루 5~6곳까지 알차게",
    }.get(pace or "", "시내는 하루 4~5곳 기준")
    season = f" 여행 시기는 {start_date.year}년 {start_date.month}월경." if start_date else ""

    prompt = (
        f"너는 '{destination}' {days_count}일 여행의 동선을 짜는 한국어 플래너다. "
        "아래 관광지·식당 목록만 사용해, 같은 날에는 지리적으로 가까운 곳끼리 묶어 "
        "되돌아가지 않는 순서로 배치하라. 연속 방문지 사이의 대략 이동시간(분)과 교통수단을 "
        "추정하고, 점심·저녁 식당은 그날 동선 근처로 고른다. "
        f"페이스는 {pace_hint}.{season} "
        "목록에 없는 장소는 쓰지 마라. 가까운 area끼리 같은 날에 모은다.\n"
        # 실제 여행 가이드 공통 규칙(다출처 검증): 시내 하루 4~5곳, 하루 1~2개 인접 구역만,
        # 근교/동반 도시 날은 이동이 길어 더 빡빡(5~6곳).
        "한 도시 가이드의 표준 페이스는 시내 하루 4~5곳이다(우리 일정엔 식사·이동도 들어가니 "
        "관광지 4~5곳이면 하루가 꽉 찬다). 하루는 인접한 1~2개 구역만 묶고 여러 구역을 "
        "넘나들지 마라(이동에 시간을 다 뺏긴다). 동반 도시·근교 당일치기 날은 이동이 길어 "
        "곳수를 5~6곳으로 더 채운다. 시내를 먼저 채우고 근교·동반 도시는 중후반 날에 둔다.\n"
        "하루 일정은 오전 10시쯤 시작해 저녁식사 전까지 큰 공백 없이 자연스럽게 이어지게 하라. "
        "마지막 관광이 대략 17~18시에 끝나도록 방문지 수와 체류시간(duration_min)을 맞추고, "
        "오후에 2시간 넘게 붕 뜨는 시간이 없게 하라. 여유로운 페이스여도 주요 명소 사이나 "
        "오후에 카페·쇼핑거리·시장·산책·전망 같은 가벼운 코스를 한두 곳 더 넣어 채워라.\n"
        f"{_weather_block(weather_by_day)}"
        f"{_multicity_block(destination, companion_days)}"
        f"{_nearby_block(nearby_options)}\n"
        f"[관광지]\n{_pool_block(attractions, 18)}\n\n"
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
