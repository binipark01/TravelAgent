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
        # 유형(전망대·야경·시장 등)을 함께 보여줘 배치기가 시간대를 맞출 수 있게 한다.
        tag = "·".join(t for t in (poi.type, poi.area) if t)
        tag = f" [{tag}]" if tag else ""
        dur = poi.recommended_duration_minutes or 90
        lines.append(f"- {poi.title}{tag} (~{dur}분)")
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


def _anchor_block(base_area: str | None, days_count: int) -> str:
    """숙소(미확정)를 대신해 추천 숙박 구역=도시 메인 부근을 일정의 기준점으로 잡는다."""
    if not base_area:
        return ""
    last = (
        " 마지막 날은 짐을 찾아 공항으로 가야 하니, 숙소 근처에서 가볍게 2~3곳만 보고"
        " 출국하는 흐름으로 짜라."
        if days_count >= 2
        else ""
    )
    return (
        "\n숙소는 아직 정해지지 않았으니 여행자들이 보통 묵는 "
        f"'{base_area}' 일대를 본거지(기준점)로 삼아라. 첫날은 공항 도착·체크인 뒤라 숙소 "
        "근처(그 일대)에서 가벼운 2~3곳으로 시작하고, 매일 동선이 본거지에서 너무 멀어지지 "
        "않게(먼 구역·근교는 중간 날에) 배치하라."
        f"{last}\n"
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


def _parse_days(raw_days: object, days_count: int) -> ArrangedItinerary | None:
    """LLM이 준 days 배열을 ArrangedItinerary로 파싱(arranger·커뮤니티 코스 공용)."""
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
                    duration_min=_coerce_int(raw_stop.get("duration_min"), 90, low=30, high=240),
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


_COMMUNITY_COURSE_CACHE: dict[str, ArrangedItinerary] = {}


def clear_community_cache() -> None:
    _COMMUNITY_COURSE_CACHE.clear()


def curate_community_course(
    destination: str,
    *,
    days_count: int,
    interests: list[str] | None,
    start_date: date | None,
) -> ArrangedItinerary | None:
    """디시·네이버 카페·블로그의 '실제 다녀온 코스 후기'를 웹검색해 day-by-day 일정을 종합한다.

    참고 카드가 아니라 일정 구조 자체를 실후기 코스에서 가져온다(이후 RouteAgent가 평점·이동
    시간·야경 시간대 규칙으로 살을 붙임). 웹검색 비활성/실패/코스 못 찾으면 None → 기존
    arrange_itinerary로 폴백.
    """
    settings = get_settings()
    if (
        not settings.enable_live_llm
        or not settings.codex_oauth_enable_web_search
        or not codex_brief_available(settings.codex_cli_command)
        or days_count < 1
    ):
        return None
    interest_text = ", ".join(i for i in (interests or []) if i and i.strip()) or "제약 없음"
    cache_key = f"{destination.strip().lower()}|{days_count}|{interest_text}"
    if cache_key in _COMMUNITY_COURSE_CACHE:
        return _COMMUNITY_COURSE_CACHE[cache_key]
    season = f" 여행 시기는 {start_date.year}년 {start_date.month}월경." if start_date else ""

    prompt = (
        "너는 한국인 여행자를 위한 일정 큐레이터다. live web search로 디시인사이드 해외여행 "
        "갤러리(gall.dcinside.com), 네이버 카페 여행 후기, 네이버 블로그에서 "
        f"'{destination} {days_count}일(또는 비슷한 기간) 코스/일정 후기' 글들을 여러 개 찾아, "
        "실제 다녀온 사람들의 대표적인 day-by-day 코스를 종합하라. 광고성 패키지·여행사 글보다 "
        f"진짜 후기를 우선한다. 여행자 취향: {interest_text}.{season}\n"
        "같은 날엔 지리적으로 가까운 곳끼리 묶어 되돌아가지 않는 순서로, 연속 방문지 사이 대략 "
        "이동시간(분)·교통수단을 추정하고, 점심·저녁 식당도 그날 동선 근처로 골라라. "
        "입장권 하나·한 단지로 묶이는 거대 명소(베르사유 궁전과 그 안의 정원·그랑/프티 트리아농, "
        "테마파크, 하나의 국립공원·유적지구)는 내부를 여러 stop으로 쪼개지 말고 한 stop으로 묶어라"
        "(title은 대표명 예 '베르사유 궁전·정원', 내부 하이라이트는 note에, duration_min 크게). "
        "그 단지 안을 이동수단으로 잇는 동선은 만들지 마라(다 같은 곳 안이다). "
        "실제 존재하는 장소만, 후기에서 자주 묶이는 동선을 반영하라. "
        f"첫날은 비행기로 도착하는 날이니 day1의 첫 stop을 '{destination}'이 실제 쓰는 주요 "
        "국제공항(도착)으로 두고(한글+원어 괄호), 공항철도/리무진으로 본거지까지 이동을 표시한 뒤 "
        "숙소 근처에서 가볍게 이어가라. 마지막 날은 출국이라 본거지 근처에서 가볍게 보고 그 날 "
        "마지막 stop을 같은 국제공항(출국)으로 끝내라(먼 일정·당일치기 금지).\n"
        "출력은 설명·코드펜스 없이 아래 JSON 객체 하나만:\n"
        "{\n"
        '  "days": [{"day":1, "area":"그날 중심 지역", "note":"실후기에서 자주 가는 동선 한줄",\n'
        '     "stops":[{"title":"정확한 장소명(한글, 원어 괄호)", "duration_min":90,\n'
        '       "travel_to_next_min":15, "travel_mode":"지하철/도보/버스"}],\n'
        '     "lunch":"식당명 또는 null", "dinner":"식당명 또는 null"}]\n'
        "}\n"
        f"{days_count}일 전부 채우고, 마지막 stop의 travel_to_next_min은 0."
    )
    data = run_codex_json(
        prompt,
        command=settings.codex_cli_command,
        model=settings.codex_oauth_model,
        reasoning_effort=settings.codex_reasoning_effort,
        timeout_seconds=min(settings.codex_oauth_timeout_seconds, 200),
        enable_web_search=True,
    )
    if not isinstance(data, dict):
        return None
    course = _parse_days(data.get("days"), days_count)
    if course is not None:
        _COMMUNITY_COURSE_CACHE[cache_key] = course
    return course


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
    base_area: str | None = None,
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
        "각 날의 곳수를 비슷하게 균형 있게 분배하라 — 한 날에 몰아넣고 다른 날을 1~2곳만 "
        "남기지 마라(시내 날은 4~5곳을 유지).\n"
        f"첫날은 비행기로 '{destination}'에 도착하는 날이다. day1의 첫 stop은 반드시 그 도시가 "
        "실제 쓰는 주요 국제공항(예: 오사카=간사이국제공항, 도쿄=나리타/하네다, 파리=샤를드골)을 "
        "'○○국제공항(도착)' 형태로 두고(한글+원어 괄호, duration_min 30), 그 stop의 "
        "travel_to_next_min·travel_mode로 공항철도/리무진버스를 타고 본거지까지 가는 이동(보통 "
        "30~75분)을 표시한 뒤, 숙소 근처에서 가벼운 2~3곳으로 이어가라. 마지막 날(출국일)은 "
        "본거지 근처에서 가벼운 1~2곳만 보고, 그 날 마지막 stop은 반드시 같은 주요 국제공항을 "
        "'○○국제공항(출국)'으로 두어 끝내라(직전 stop→공항 이동을 travel로 표시). 먼 근교· "
        "당일치기·동반 도시는 절대 마지막 날에 넣지 마라(비행기를 놓친다).\n"
        "시간대 적합성을 반드시 지켜라(목록의 [유형] 참고): 야경·전망대·전망·나이트뷰·바·"
        "나이트라이프는 그날 동선의 '마지막'(해질녘~저녁)에 두고, 절대 오전에 넣지 마라. "
        "새벽시장·일출 명소는 오전 앞쪽에, 박물관·미술관 등 실내는 한낮이나 비 오는 시간대에 "
        "배치하라. 같은 area 안에서는 이 시간대 규칙이 지리 순서보다 우선이다.\n"
        "입장권 하나·한 단지로 묶이는 거대 명소(예: 베르사유 궁전과 그 안의 정원·그랑/프티 "
        "트리아농, 디즈니·유니버설 같은 테마파크, 하나의 국립공원·유적지구)는 내부를 여러 stop으로 "
        "쪼개지 마라 — 한 stop으로 묶어 title은 대표명(예 '베르사유 궁전·정원'), duration_min을 "
        "크게(240~480) 주고, 내부 하이라이트(정원·트리아농 등)는 note에 적어라. 그 단지 안을 "
        "이동수단으로 잇는 동선(transfer)을 만들지 마라(다 같은 곳 안이라 우습게 보인다). "
        "목록의 그 내부 명소들은 이 한 stop에 묶이므로 '한 번씩 써라' 규칙의 예외다.\n"
        f"{_weather_block(weather_by_day)}"
        f"{_anchor_block(base_area, days_count)}"
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
    return _parse_days(data.get("days"), days_count)
