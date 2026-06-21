"""LLM(Codex) 웹검색으로 관광지·식당·근교를 '종합 추천'하는 큐레이터.

구글지도 평점순 정렬만으로는 "스시집만" 나오거나 흩어진 현지 정보(네이버 블로그·카페·
여행갤·공식관광청)를 못 살린다. 여기서는 Codex의 live web search(`--search`)로 그 정보를
종합해 **재추천 + 추천 이유 + 출처**를 붙여 돌려준다. 구글지도 후보군을 grounding으로 넘겨
실재하는 곳을 우선 쓰되, 여러 출처가 강하게 미는 '숨은 명소'는 풀 밖이라도 추가한다.

라이브 LLM/웹검색이 꺼져 있으면 None을 돌려주어 호출부가 기존 구글지도/카탈로그 결과를
그대로 쓰게 한다(오프라인 테스트 영향 없음). 같은 (목적지·관심사)는 프로세스당 1회 캐시.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from urllib.parse import quote_plus

from travel_agent.app.agents.llm_client import codex_brief_available, run_codex_json
from travel_agent.app.config import Settings, get_settings
from travel_agent.app.llm.source_guide import source_hints_block
from travel_agent.app.schemas.common import Location, Money, SourceRef
from travel_agent.app.schemas.providers import (
    CitySegment,
    IntercityLeg,
    LocalEvent,
    LocalEventsGuide,
    MultiCityPlan,
    NearbyDestination,
    NearbyGuide,
    POIOption,
    PrepChecklist,
    PrepGroup,
    ProviderMetadata,
    StayArea,
    StayAreaGuide,
)
from travel_agent.app.utils.ids import new_id
from travel_agent.app.utils.time import expires_in, utc_now


@dataclass(frozen=True)
class CuratedPois:
    attractions: list[POIOption]
    restaurants: list[POIOption]


# 같은 (목적지·관심사·kind)는 한 번만 웹검색한다(웹검색이 비싸서).
_CITY_CACHE: dict[str, CuratedPois] = {}
_NEARBY_CACHE: dict[str, NearbyGuide] = {}
_STAY_CACHE: dict[str, StayAreaGuide] = {}
_CHECK_CACHE: dict[str, PrepChecklist] = {}
_MULTICITY_CACHE: dict[str, MultiCityPlan] = {}
_EVENTS_CACHE: dict[str, LocalEventsGuide] = {}


def clear_cache() -> None:
    """테스트용: 큐레이션 캐시를 비운다."""
    _CITY_CACHE.clear()
    _NEARBY_CACHE.clear()
    _STAY_CACHE.clear()
    _CHECK_CACHE.clear()
    _MULTICITY_CACHE.clear()
    _EVENTS_CACHE.clear()


def _enabled(settings: Settings) -> bool:
    return (
        settings.enable_live_llm
        and settings.codex_oauth_enable_web_search
        and codex_brief_available(settings.codex_cli_command)
    )


def _run(prompt: str, settings: Settings) -> dict | None:
    return run_codex_json(
        prompt,
        command=settings.codex_cli_command,
        model=settings.codex_oauth_model,
        reasoning_effort=settings.codex_reasoning_effort,
        timeout_seconds=min(settings.codex_oauth_timeout_seconds, 200),
        enable_web_search=True,
    )


def _maps_url(place: str, destination: str) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(f'{place} {destination}')}"


def _llm_metadata(source_url: str) -> ProviderMetadata:
    now = utc_now()
    source_ref = SourceRef(
        source_id=new_id("src"),
        provider="llm_curation",
        source_url=source_url,
        title="LLM 웹검색 종합 추천(블로그·카페·관광청 등)",
        reference=f"llm-curation-{now.strftime('%Y%m%d%H%M%S')}",
        retrieved_at=now,
        expires_at=expires_in(12),
        is_live=True,
        is_mock=False,
        source_type="llm_web_synthesis",
        confidence=0.55,
        freshness_note="여러 웹 출처를 LLM이 종합한 추천. 영업시간·가격은 방문 전 재확인 필요.",
    )
    return ProviderMetadata(
        provider_name="llm_curation",
        retrieved_at=now,
        source_ref=source_ref,
        expires_at=expires_in(12),
        normalized_currency=None,
        is_mock=False,
    )


def _clean_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if isinstance(v, str) and v.strip()]


def _clean_str(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _coerce_rating(value: object) -> float | None:
    try:
        rating = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return rating if 0 < rating <= 5 else None


def _poi_from_item(
    item: dict, destination: str, currency: str, *, default_type: str
) -> POIOption | None:
    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    name = name.strip()
    raw_type = (item.get("type") or item.get("cuisine") or "").strip()
    poi_type = raw_type or default_type
    area = (item.get("area") or "").strip() or poi_type
    why = (item.get("why") or "").strip()
    sources = _clean_list(item.get("sources"))
    primary_source = sources[0] if sources else _maps_url(name, destination)

    notes: list[str] = []
    if why:
        notes.append(f"💡 {why}")
    if sources:
        notes.append("📝 출처: " + " · ".join(sources[:3]))
    notes.append("LLM 웹검색 종합 추천 · 방문 전 영업시간·예약 확인")

    duration = item.get("duration_min")
    try:
        duration = int(duration)
    except (TypeError, ValueError):
        duration = 90
    duration = max(30, min(duration, 240))

    booking_required = bool(item.get("booking_required"))
    booking_url = _clean_str(item.get("booking_url"))
    if booking_required and booking_url:
        notes.insert(0, "🎟 사전 예매 권장")

    return POIOption(
        poi_id=new_id("poi"),
        title=name,
        type=poi_type,
        location=Location(name=destination, country=None, area=area),
        area=area,
        estimated_cost=Money(amount=0, currency=currency),
        rating=_coerce_rating(item.get("rating")),
        review_count=None,
        opening_hours=None,
        recommended_duration_minutes=duration,
        booking_required=booking_required,
        booking_url=booking_url,
        metadata=_llm_metadata(primary_source),
        notes=notes,
    )


def _pool_names(pool: list[POIOption], limit: int = 18) -> str:
    names = []
    for poi in pool[:limit]:
        rating = f" ({poi.rating}★)" if poi.rating else ""
        names.append(f"{poi.title}{rating}")
    return ", ".join(names) if names else "(없음)"


def _season_hint(start_date: date | None) -> str:
    if not start_date:
        return ""
    return f" 여행 시기는 {start_date.year}년 {start_date.month}월경이다."


def curate_city_pois(
    destination: str,
    *,
    interests: list[str],
    start_date: date | None,
    currency: str,
    attraction_pool: list[POIOption],
    restaurant_pool: list[POIOption],
) -> CuratedPois | None:
    """관광지·식당을 웹검색으로 종합 재추천한다. 비활성/실패 시 None."""
    settings = get_settings()
    if not _enabled(settings):
        return None
    interest_text = ", ".join(i for i in interests if i and i.strip()) or "특별한 제약 없음"
    cache_key = f"{destination.strip().lower()}|{interest_text}"
    if cache_key in _CITY_CACHE:
        return _CITY_CACHE[cache_key]

    prompt = (
        "너는 한국인 여행자를 위한 현지 큐레이터다. live web search로 네이버 블로그·카페, "
        "여행 커뮤니티(디시 여행갤 등), 구글 리뷰, 공식 관광청 정보를 두루 검색해 "
        f"'{destination}'의 관광지와 맛집을 종합 추천하라.\n"
        f"여행자 관심사: {interest_text}.{_season_hint(start_date)}\n"
        "단순 별점순이 아니라 현지 평판·혼잡도·계절성·가성비를 함께 보고 고른다. "
        "맛집은 한 종류(예: 스시)만 몰리지 않게 음식 종류를 다양하게 섞어라. "
        "관광지도 한 유형(예: 사원만·미술관만)에 몰리지 않게 전망대·거리·시장·공원·체험·"
        "야경 등 유형을 다양하게 섞어라. 관심사는 반영하되 같은 유형은 4곳을 넘기지 마라.\n"
        f"{source_hints_block(destination)}\n"
        "아래 구글지도 후보를 참고하되(실재하는 곳 위주), 여러 출처가 강하게 추천하는 "
        "'숨은 명소'는 후보에 없어도 추가해도 된다. 단 실제로 존재하는 곳만. 각 항목에는 "
        "반드시 실제 근거 출처 URL(블로그·리뷰·공식 사이트)을 1개 이상 'sources'에 넣어라. "
        "출처를 못 찾는 곳은 추천하지 마라(구글지도 검색 링크는 출처가 아니다).\n"
        f"[관광지 후보] {_pool_names(attraction_pool)}\n"
        f"[맛집 후보] {_pool_names(restaurant_pool)}\n\n"
        "루브르·에펠탑·바티칸처럼 시간지정 입장권·사전 예매가 사실상 필수인 곳은 "
        '"booking_required":true와 함께 예매 링크("booking_url")를 위 권위 액티비티 '
        "플랫폼(Klook·GetYourGuide 등)이나 공식 예매 페이지로 달아라. 예매가 필요 없으면 "
        "booking_required는 false.\n"
        "출력은 설명·코드펜스 없이 아래 JSON 객체 하나만:\n"
        "{\n"
        '  "attractions": [{"name":"", "type":"전망대/사원/거리 등", "area":"동네/지역", '
        '"why":"왜 추천하는지 1~2문장(현지평·시즌 등)", "duration_min":90, "rating":4.5, '
        '"booking_required":false, "booking_url":null, "sources":["url"]}],\n'
        '  "restaurants": [{"name":"", "cuisine":"스시/라멘/이자카야 등", "area":"", '
        '"why":"", "rating":4.4, "sources":["url"]}]\n'
        "}\n"
        "관광지 6~10곳, 맛집 6~10곳."
    )
    data = _run(prompt, settings)
    if not isinstance(data, dict):
        return None
    attractions = [
        poi
        for raw in (data.get("attractions") or [])
        if isinstance(raw, dict)
        and (poi := _poi_from_item(raw, destination, currency, default_type="관광지"))
    ]
    restaurants = [
        poi
        for raw in (data.get("restaurants") or [])
        if isinstance(raw, dict)
        and (poi := _poi_from_item(raw, destination, currency, default_type="맛집"))
    ]
    if not attractions and not restaurants:
        return None
    curated = CuratedPois(attractions=attractions, restaurants=restaurants)
    _CITY_CACHE[cache_key] = curated
    return curated


def curate_nearby(destination: str) -> NearbyGuide | None:
    """근교 당일치기를 웹검색으로 종합 추천한다. 비활성/실패 시 None."""
    settings = get_settings()
    if not _enabled(settings):
        return None
    cache_key = destination.strip().lower()
    if cache_key in _NEARBY_CACHE:
        return _NEARBY_CACHE[cache_key]

    prompt = (
        "너는 한국인 여행자를 위한 현지 큐레이터다. live web search로 네이버 블로그·카페, "
        "여행 커뮤니티, 공식 관광청 정보를 검색해 "
        f"'{destination}'에서 기차·버스·렌터카로 닿는 **근교 당일치기** 명소를 종합 추천하라.\n"
        f"{source_hints_block(destination)}\n"
        "각 명소의 대략 이동시간·교통수단·볼거리를 적고, 근거 출처 URL을 최소 1개 붙여라. "
        "실제 존재하는 곳만, 지어내지 마라. 적당한 근교가 거의 없으면 destinations를 빈 배열로.\n\n"
        "출력은 설명·코드펜스 없이 아래 JSON 객체 하나만:\n"
        "{\n"
        f'  "hub": "{destination}",\n'
        '  "summary": "근교 당일치기 한두 문장 요약",\n'
        '  "destinations": [{"name":"오타루", "travel_time":"JR 약 35분", '
        '"transport":"JR 쾌속", "highlights":["운하","스시"], "best_for":"반나절~하루", '
        '"sources":["url"]}]\n'
        "}\n"
        "근교 3~6곳."
    )
    data = _run(prompt, settings)
    if not isinstance(data, dict):
        return None
    raw_destinations = data.get("destinations")
    if not isinstance(raw_destinations, list) or not raw_destinations:
        return None
    destinations: list[NearbyDestination] = []
    for raw in raw_destinations:
        if not isinstance(raw, dict):
            continue
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        sources = _clean_list(raw.get("sources"))
        destinations.append(
            NearbyDestination(
                name=name.strip(),
                travel_time=(raw.get("travel_time") or "이동시간 확인 필요").strip(),
                transport=(raw.get("transport") or "교통편 확인 필요").strip(),
                highlights=_clean_list(raw.get("highlights")),
                best_for=(raw.get("best_for") or "").strip() or None,
                source_url=sources[0] if sources else None,
            )
        )
    if not destinations:
        return None
    hub = (data.get("hub") or destination).strip() or destination
    summary = (data.get("summary") or f"{hub} 근교 당일치기 추천").strip()
    guide = NearbyGuide(
        hub=hub,
        summary=summary,
        destinations=destinations,
        source_url=destinations[0].source_url,
        metadata=_llm_metadata(destinations[0].source_url or _maps_url(hub, destination)),
    )
    _NEARBY_CACHE[cache_key] = guide
    return guide


def curate_stay_areas(destination: str) -> StayAreaGuide | None:
    """'어느 동네에 묵을지'를 웹검색으로 종합 추천한다. 비활성/실패 시 None."""
    settings = get_settings()
    if not _enabled(settings):
        return None
    cache_key = destination.strip().lower()
    if cache_key in _STAY_CACHE:
        return _STAY_CACHE[cache_key]

    prompt = (
        "너는 한국인 여행자를 위한 현지 큐레이터다. live web search로 네이버 블로그·카페, "
        "여행 커뮤니티, 호텔 예약 가이드를 검색해 "
        f"'{destination}'에서 **숙소를 어느 동네/구역에 잡으면 좋은지**를 종합 추천하라.\n"
        f"{source_hints_block(destination)}\n"
        "각 구역의 분위기, 어떤 여행자/목적에 맞는지, 치안·가격대·교통 접근성 팁을 적고 "
        "근거 출처 URL을 최소 1개 붙여라. 실제 존재하는 구역만, 지어내지 마라.\n\n"
        "출력은 설명·코드펜스 없이 아래 JSON 객체 하나만:\n"
        "{\n"
        f'  "destination": "{destination}",\n'
        '  "summary": "이 도시 숙소 구역 선택 한두 문장 요약",\n'
        '  "areas": [{"name":"르마레(Le Marais)", "vibe":"감성 카페·편집숍 골목", '
        '"good_for":["미술관 도보","야경·디너"], "note":"치안·가격·교통 팁", '
        '"source_url":"url"}]\n'
        "}\n"
        "구역 3~5곳."
    )
    data = _run(prompt, settings)
    if not isinstance(data, dict):
        return None
    raw_areas = data.get("areas")
    if not isinstance(raw_areas, list) or not raw_areas:
        return None
    areas: list[StayArea] = []
    for raw in raw_areas:
        if not isinstance(raw, dict):
            continue
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        areas.append(
            StayArea(
                name=name.strip(),
                vibe=(raw.get("vibe") or "").strip(),
                good_for=_clean_list(raw.get("good_for")),
                note=_clean_str(raw.get("note")),
                source_url=_clean_str(raw.get("source_url")),
            )
        )
    if not areas:
        return None
    summary = (data.get("summary") or f"{destination} 추천 숙박 구역").strip()
    first_source = next((a.source_url for a in areas if a.source_url), None)
    guide = StayAreaGuide(
        destination=destination,
        summary=summary,
        areas=areas,
        source_url=first_source,
        metadata=_llm_metadata(first_source or _maps_url(destination, destination)),
    )
    _STAY_CACHE[cache_key] = guide
    return guide


def curate_events(
    destination: str, start_date: date | None, end_date: date | None
) -> LocalEventsGuide | None:
    """여행 날짜에 목적지에서 열리는 축제·전시·행사를 웹검색으로 찾는다.

    실제로 그 기간에 열리는 것만, 출처와 함께. 없으면(또는 비활성/실패) None → 카드 미표시.
    날짜를 모르면 그 도시의 대표 시즌 행사를 안내한다.
    """
    settings = get_settings()
    if not _enabled(settings):
        return None
    if start_date and end_date:
        date_label = f"{start_date.isoformat()} ~ {end_date.isoformat()}"
        when = f"여행 기간은 {date_label}이다. 이 기간과 겹치는 행사를 우선하라."
    else:
        date_label = ""
        when = "구체적 날짜를 모르니 그 도시의 대표적인 시즌 축제·연례 행사를 알려줘라."
    cache_key = f"{destination.strip().lower()}|{date_label}"
    if cache_key in _EVENTS_CACHE:
        return _EVENTS_CACHE[cache_key]

    prompt = (
        "너는 한국인 여행자를 위한 현지 큐레이터다. live web search로 관광청·공식 행사 페이지, "
        "지역 뉴스, 네이버 블로그·카페를 검색해 "
        f"'{destination}'에서 열리는 축제·전시·콘서트·시장·스포츠 등 여행자가 갈 만한 행사를 "
        f"정리하라. {when}\n"
        f"{source_hints_block(destination)}\n"
        "반드시 실제로 그 시기에 열리는 행사만 적고, 각 행사에 근거 출처 URL을 붙여라. "
        "출처를 못 찾거나 그 기간에 열리는지 불확실하면 빼라(지어내지 마라). "
        "해당 기간에 특별한 행사가 없으면 events를 빈 배열로 둬라.\n\n"
        "출력은 설명·코드펜스 없이 아래 JSON 객체 하나만:\n"
        "{\n"
        f'  "destination": "{destination}",\n'
        '  "summary": "이 시기 행사 분위기 한두 문장(없으면 그렇게)",\n'
        '  "events": [{"name":"기온 마쓰리", "category":"축제", "period":"7/17~24", '
        '"venue":"야사카 신사 일대", "highlight":"교토 3대 축제, 야마보코 순행", '
        '"source_url":"url"}]\n'
        "}\n"
        "행사 최대 6개, 여행 기간과 가까운 순."
    )
    data = _run(prompt, settings)
    if not isinstance(data, dict):
        return None
    raw_events = data.get("events")
    if not isinstance(raw_events, list):
        return None
    events: list[LocalEvent] = []
    for raw in raw_events:
        if not isinstance(raw, dict):
            continue
        name = raw.get("name")
        source_url = _clean_str(raw.get("source_url"))
        # 출처 없는 행사는 신뢰할 수 없으니 버린다(없는 행사 지어내기 방지).
        if not isinstance(name, str) or not name.strip() or not source_url:
            continue
        events.append(
            LocalEvent(
                name=name.strip(),
                category=(raw.get("category") or "행사").strip(),
                period=(raw.get("period") or "").strip(),
                venue=_clean_str(raw.get("venue")),
                highlight=_clean_str(raw.get("highlight")),
                source_url=source_url,
            )
        )
    if not events:
        return None
    summary = (data.get("summary") or f"{destination} 여행 기간 행사").strip()
    first_source = next((e.source_url for e in events if e.source_url), None)
    guide = LocalEventsGuide(
        destination=destination,
        date_range=date_label,
        summary=summary,
        events=events,
        source_url=first_source,
        metadata=_llm_metadata(first_source or _maps_url(destination, destination)),
    )
    _EVENTS_CACHE[cache_key] = guide
    return guide


def curate_checklist(destination: str, *, context: str) -> PrepChecklist | None:
    """출발 전 준비물·할 일 체크리스트를 LLM이 정리한다. 비활성/실패 시 None.

    전압/플러그·유심·환전 등은 안정적 지식이라 웹검색 없이 추론한다(빠름). 비자·날씨 같은
    여행별 사실은 호출부가 context로 넘긴다.
    """
    settings = get_settings()
    if not _enabled(settings):
        return None
    cache_key = f"{destination.strip().lower()}|{context}"
    if cache_key in _CHECK_CACHE:
        return _CHECK_CACHE[cache_key]

    prompt = (
        "너는 한국인 여행자를 위한 출발 전 준비물·체크리스트 도우미다. 아래 여행에 맞춰 "
        "준비물·할 일을 카테고리별로 정리하라. 전압/플러그 타입, 유심/이심, 환전·카드, "
        "날씨에 맞는 옷차림, 비자·서류, 상비약, 현지 앱·교통카드 등을 목적지·계절에 맞게 "
        "구체적으로. 일반론만 늘어놓지 말고 이 목적지 특성을 반영하라.\n"
        f"여행 정보: {context}\n\n"
        "출력은 설명·코드펜스 없이 JSON 하나만:\n"
        "{\n"
        f'  "destination": "{destination}",\n'
        '  "summary": "한두 문장 요약",\n'
        '  "groups": [{"title":"전자·전압", "items":["C타입 어댑터(220V)","보조배터리"]}]\n'
        "}\n"
        "카테고리 4~7개, 각 항목은 짧게."
    )
    data = run_codex_json(
        prompt,
        command=settings.codex_cli_command,
        model=settings.codex_oauth_model,
        reasoning_effort=settings.codex_reasoning_effort,
        timeout_seconds=min(settings.codex_oauth_timeout_seconds, 90),
    )
    if not isinstance(data, dict):
        return None
    raw_groups = data.get("groups")
    if not isinstance(raw_groups, list) or not raw_groups:
        return None
    groups: list[PrepGroup] = []
    for raw in raw_groups:
        if not isinstance(raw, dict):
            continue
        title = _clean_str(raw.get("title"))
        items = _clean_list(raw.get("items"))
        if title and items:
            groups.append(PrepGroup(title=title, items=items[:8]))
    if not groups:
        return None
    summary = (data.get("summary") or f"{destination} 여행 준비물").strip()
    checklist = PrepChecklist(
        destination=destination,
        summary=summary,
        groups=groups,
        metadata=_llm_metadata(_maps_url(destination, destination)),
    )
    _CHECK_CACHE[cache_key] = checklist
    return checklist


def _coerce_nights(value: object, default: int) -> int:
    try:
        nights = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(1, min(nights, 30))


def curate_multicity(
    destinations: list[str], *, total_days: int | None
) -> MultiCityPlan | None:
    """복수 목적지의 도시별 일수 배분 + 도시간 이동을 LLM 웹검색으로 정리한다.

    도시간 기차/항공 소요·예매처는 변동 정보라 web search를 쓴다. 비활성/실패 시 None.
    """
    settings = get_settings()
    if not _enabled(settings) or len(destinations) < 2:
        return None
    cities = ", ".join(destinations)
    cache_key = cities.lower()
    if cache_key in _MULTICITY_CACHE:
        return _MULTICITY_CACHE[cache_key]

    days_hint = f"총 {total_days}일을 도시별로 합리적으로 배분하라." if total_days else ""
    prompt = (
        "너는 한국인 여행자를 위한 멀티시티 동선 플래너다. live web search로 도시간 이동수단·"
        f"소요시간·예매처를 확인해 '{cities}' 여행을 정리하라.\n"
        f"방문 순서를 효율적으로 정하고, 각 도시 추천 숙박일수와 핵심 볼거리, 도시간 이동"
        f"(기차/항공/버스, 대략 소요, 예매처)을 적어라. {days_hint} 출처는 신뢰 가능한 곳만.\n\n"
        "출력은 설명·코드펜스 없이 JSON 하나만:\n"
        "{\n"
        '  "summary": "전체 동선 한두 문장",\n'
        '  "segments": [{"city":"파리", "nights":3, "highlights":["루브르","에펠탑"]}],\n'
        '  "legs": [{"origin":"파리", "destination":"런던", "mode":"기차(유로스타)", '
        '"duration":"약 2시간 20분", "booking_hint":"eurostar.com"}],\n'
        '  "tips": ["도시간 이동권은 미리 예매가 저렴"]\n'
        "}"
    )
    data = _run(prompt, settings)
    if not isinstance(data, dict):
        return None
    segments: list[CitySegment] = []
    for raw in data.get("segments") or []:
        if not isinstance(raw, dict):
            continue
        city = _clean_str(raw.get("city"))
        if not city:
            continue
        segments.append(
            CitySegment(
                city=city,
                nights=_coerce_nights(raw.get("nights"), 2),
                highlights=_clean_list(raw.get("highlights")),
            )
        )
    if not segments:
        return None
    legs: list[IntercityLeg] = []
    for raw in data.get("legs") or []:
        if not isinstance(raw, dict):
            continue
        origin = _clean_str(raw.get("origin"))
        dest = _clean_str(raw.get("destination"))
        if not origin or not dest:
            continue
        legs.append(
            IntercityLeg(
                origin=origin,
                destination=dest,
                mode=(raw.get("mode") or "이동").strip() or "이동",
                duration=(raw.get("duration") or "소요시간 확인").strip() or "소요시간 확인",
                booking_hint=_clean_str(raw.get("booking_hint")),
            )
        )
    plan = MultiCityPlan(
        destinations=destinations,
        summary=(data.get("summary") or f"{cities} 멀티시티 동선").strip(),
        segments=segments,
        legs=legs,
        tips=_clean_list(data.get("tips")),
        metadata=_llm_metadata(_maps_url(destinations[0], destinations[0])),
    )
    _MULTICITY_CACHE[cache_key] = plan
    return plan
