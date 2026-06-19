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
    NearbyDestination,
    NearbyGuide,
    POIOption,
    ProviderMetadata,
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


def clear_cache() -> None:
    """테스트용: 큐레이션 캐시를 비운다."""
    _CITY_CACHE.clear()
    _NEARBY_CACHE.clear()


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
        booking_required=False,
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
        "맛집은 한 종류(예: 스시)만 몰리지 않게 음식 종류를 다양하게 섞어라.\n"
        f"{source_hints_block(destination)}\n"
        "아래 구글지도 후보를 참고하되(실재하는 곳 위주), 여러 출처가 강하게 추천하는 "
        "'숨은 명소'는 후보에 없어도 추가해도 된다. 단 실제로 존재하는 곳만, 그리고 각 항목에 "
        "근거 출처 URL을 최소 1개 붙여라(지어내지 마라).\n"
        f"[관광지 후보] {_pool_names(attraction_pool)}\n"
        f"[맛집 후보] {_pool_names(restaurant_pool)}\n\n"
        "출력은 설명·코드펜스 없이 아래 JSON 객체 하나만:\n"
        "{\n"
        '  "attractions": [{"name":"", "type":"전망대/사원/거리 등", "area":"동네/지역", '
        '"why":"왜 추천하는지 1~2문장(현지평·시즌 등)", "duration_min":90, "rating":4.5, '
        '"sources":["url"]}],\n'
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
