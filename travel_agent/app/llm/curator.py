"""LLM(Codex) 웹검색으로 관광지·식당·근교를 '종합 추천'하는 큐레이터.

구글지도 평점순 정렬만으로는 "스시집만" 나오거나 흩어진 현지 정보(네이버 블로그·카페·
여행갤·공식관광청)를 못 살린다. 여기서는 Codex의 live web search(`--search`)로 그 정보를
종합해 **재추천 + 추천 이유 + 출처**를 붙여 돌려준다. 구글지도 후보군을 grounding으로 넘겨
실재하는 곳을 우선 쓰되, 여러 출처가 강하게 미는 '숨은 명소'는 풀 밖이라도 추가한다.

라이브 LLM/웹검색이 꺼져 있으면 None을 돌려주어 호출부가 기존 구글지도/카탈로그 결과를
그대로 쓰게 한다(오프라인 테스트 영향 없음). 같은 (목적지·관심사)는 프로세스당 1회 캐시.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import TypeVar
from urllib.parse import quote_plus

from travel_agent.app.agents.llm_client import live_llm_web_enabled, run_codex_json
from travel_agent.app.config import Settings, get_settings
from travel_agent.app.llm.source_guide import source_hints_block
from travel_agent.app.schemas.common import Location, Money, SourceRef
from travel_agent.app.schemas.providers import (
    CitySegment,
    IntercityLeg,
    LocalEvent,
    LocalEventsGuide,
    LocalTransportItem,
    LocalTransportPlan,
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


@dataclass(frozen=True)
class CompanionCity:
    """그 도시 여행에서 대다수가 함께 묶는 '핵심 동반 도시'(예: 오사카의 교토)."""

    city: str
    days: int  # 보통 배분하는 일수
    reason: str
    source_url: str | None


# 같은 (목적지·관심사·kind)는 한 번만 웹검색한다(웹검색이 비싸서).
_CITY_CACHE: dict[str, CuratedPois] = {}
_NEARBY_CACHE: dict[str, NearbyGuide] = {}
_STAY_CACHE: dict[str, StayAreaGuide] = {}
_CHECK_CACHE: dict[str, PrepChecklist] = {}
_MULTICITY_CACHE: dict[str, MultiCityPlan] = {}
_EVENTS_CACHE: dict[str, LocalEventsGuide] = {}
_COMPANION_CACHE: dict[str, list[CompanionCity]] = {}
_LOCALTRANS_CACHE: dict[str, LocalTransportPlan] = {}
_RECOMMEND_CACHE: dict[str, list[str]] = {}

# route_optimizer._prefetch_route_lookups가 근교·숙박구역·동반도시 큐레이션을 병렬로 돌려
# 이 모듈의 캐시에 동시에 접근한다. 락으로 check-then-set의 dict race를 닫는다.
_CACHE_LOCK = threading.Lock()

_T = TypeVar("_T")


def _cached(cache: dict[str, _T], key: str, compute: Callable[[], _T | None]) -> _T | None:
    """캐시 read/write만 락으로 보호한다(compute=LLM 호출은 락 밖에서).

    트레이드오프: cold 캐시에서 동일 키로 동시에 들어온 두 호출이 각자 compute할 수 있다
    (드물고 결과는 동일). 대신 compute(수십 초 웹검색)를 락 안에서 잡지 않아 서로 다른 키의
    병렬 큐레이션이 직렬화되지 않는다 — _prefetch_route_lookups의 병렬성을 살린다.
    """
    with _CACHE_LOCK:
        if key in cache:
            return cache[key]
    result = compute()
    if result is not None:
        with _CACHE_LOCK:
            cache[key] = result
    return result


def clear_cache() -> None:
    """테스트용: 큐레이션 캐시를 비운다."""
    with _CACHE_LOCK:
        _CITY_CACHE.clear()
        _NEARBY_CACHE.clear()
        _STAY_CACHE.clear()
        _CHECK_CACHE.clear()
        _MULTICITY_CACHE.clear()
        _EVENTS_CACHE.clear()
        _COMPANION_CACHE.clear()
        _LOCALTRANS_CACHE.clear()
        _RECOMMEND_CACHE.clear()


def _enabled(settings: Settings) -> bool:
    return live_llm_web_enabled(settings)


def _run(prompt: str, settings: Settings) -> dict | None:
    # 타임아웃·빈응답·파싱실패(=None)는 transient라 1회 재시도한다. 정상적인 '빈 결과'(근교
    # 없음 등)는 run_codex_json이 dict를 돌려주므로 재시도 대상이 아니다 — 진짜 없는 카드의
    # 대기시간을 2배로 늘리지 않으면서 가끔 비는 카드(체크리스트 등)만 살린다.
    for _ in range(2):
        result = run_codex_json(
            prompt,
            command=settings.codex_cli_command,
            model=settings.codex_oauth_model,
            reasoning_effort=settings.codex_reasoning_effort,
            timeout_seconds=min(settings.codex_oauth_timeout_seconds, 200),
            enable_web_search=True,
        )
        if result is not None:
            return result
    return None


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


def _season_key(start_date: date | None) -> str:
    """캐시 키에 넣을 시즌(월). 프롬프트는 시즌을 반영하므로 키에도 넣어야
    첫 호출의 시즌(예: 6월 추천)이 다른 달 요청에 고착되지 않는다."""
    return str(start_date.month) if start_date else ""


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
    # 시즌(월)·통화를 키에 포함 — 프롬프트가 둘에 의존하므로 첫 호출 값이 고착되면 안 된다.
    cache_key = (
        f"{destination.strip().lower()}|{interest_text}|{_season_key(start_date)}|{currency}"
    )

    prompt = (
        "너는 한국인 여행자를 위한 현지 큐레이터다. live web search로 네이버 블로그·카페, "
        "여행 커뮤니티(디시 여행갤 등), 구글 리뷰, 공식 관광청 정보를 두루 검색해 "
        f"'{destination}'의 관광지와 맛집을 종합 추천하라.\n"
        f"여행자 관심사: {interest_text}.{_season_hint(start_date)}\n"
        "단순 별점순이 아니라 현지 평판·혼잡도·계절성·가성비를 함께 보고 고른다. "
        "무엇보다 **실제로 그 도시 여행자(특히 한국인 블로그·커뮤니티 후기)가 많이 가는 인기 "
        "명소**를 우선하라. 학술적 유적·소규모 로컬 박물관·동네 명소처럼 일반 여행자는 잘 안 "
        "가는 곳은 빼라(그 도시 대표 명소 TOP에 드는 경우만 예외). 유형 다양성보다 '실제 인기·"
        "방문 빈도'가 우선이며, 인기 명소가 부족하면 niche한 곳으로 억지로 개수를 채우지 말고 "
        "그냥 적게 추천하라(빈 시간은 일정 배치기가 카페·거리로 채운다).\n"
        "맛집은 한 종류(예: 스시)만 몰리지 않게 음식 종류를 다양하게 섞어라. "
        "관광지도 한 유형(예: 사원만·미술관만)에 몰리지 않게 전망대·거리·시장·공원·체험·"
        "야경 등 유형을 섞되, 인기 없는 곳을 다양성 명목으로 넣지는 마라. 같은 유형은 4곳을 "
        "넘기지 마라.\n"
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
        "모든 'name'·'area'는 한국어(한글)로 적어라 — 한국에서 통용되는 한글 표기가 있으면 "
        "그걸 쓰고, 없으면 현지 발음을 한글로 옮긴 뒤 검색·지도용 원어명을 괄호로 병기하라"
        "(예: 기요미즈데라(清水寺), 이치란(一蘭), 오토야(大戸屋)). 일본어·현지어·로마자를 "
        "그대로 두지 마라(세계적으로 영문 고유명사로 통하는 브랜드는 예외).\n"
        "출력은 설명·코드펜스 없이 아래 JSON 객체 하나만:\n"
        "{\n"
        '  "attractions": [{"name":"", "type":"전망대/사원/거리 등", "area":"동네/지역", '
        '"why":"왜 추천하는지 1~2문장(현지평·시즌 등)", "duration_min":90, "rating":4.5, '
        '"booking_required":false, "booking_url":null, "sources":["url"]}],\n'
        '  "restaurants": [{"name":"", "cuisine":"스시/라멘/이자카야 등", "area":"", '
        '"why":"", "rating":4.4, "sources":["url"]}]\n'
        "}\n"
        "관광지 8~14곳, 맛집 8~12곳(인기 명소가 많은 대도시는 넉넉히, 명소가 적은 작은 도시는 "
        "진짜 갈 만한 곳만 적게 — niche padding 금지)."
    )
    def compute() -> CuratedPois | None:
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
        return CuratedPois(attractions=attractions, restaurants=restaurants)

    return _cached(_CITY_CACHE, cache_key, compute)


def curate_nearby(destination: str) -> NearbyGuide | None:
    """근교 당일치기를 웹검색으로 종합 추천한다. 비활성/실패 시 None."""
    settings = get_settings()
    if not _enabled(settings):
        return None
    cache_key = destination.strip().lower()

    prompt = (
        "너는 한국인 여행자를 위한 현지 큐레이터다. live web search로 네이버 블로그·카페, "
        "여행 커뮤니티, 공식 관광청 정보를 검색해 "
        f"'{destination}'에서 기차·버스·렌터카로 닿는 **근교 당일치기** 명소를 종합 추천하라.\n"
        f"{source_hints_block(destination)}\n"
        "각 명소의 대략 이동시간·교통수단·볼거리를 적고, 근거 출처 URL을 최소 1개 붙여라. "
        "travel_time은 대표 경로 하나로 짧게(예: 'JR 약 35분', '버스 1시간'). 여러 경로·"
        "범위를 길게 나열하지 마라(8자 안팎). transport도 한 수단만 간단히.\n"
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
    def compute() -> NearbyGuide | None:
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
        return NearbyGuide(
            hub=hub,
            summary=summary,
            destinations=destinations,
            source_url=destinations[0].source_url,
            metadata=_llm_metadata(destinations[0].source_url or _maps_url(hub, destination)),
        )

    return _cached(_NEARBY_CACHE, cache_key, compute)


def _transport_items(raw_list: object, category: str) -> list[LocalTransportItem]:
    """LLM이 준 교통 항목 배열을 LocalTransportItem 리스트로 변환(이름 없으면 건너뜀)."""
    items: list[LocalTransportItem] = []
    if not isinstance(raw_list, list):
        return items
    for raw in raw_list:
        if not isinstance(raw, dict):
            continue
        name = _clean_str(raw.get("name"))
        if not name:
            continue
        sources = _clean_list(raw.get("sources"))
        items.append(
            LocalTransportItem(
                category=category,
                name=name,
                detail=_clean_str(raw.get("detail")) or "",
                price=_clean_str(raw.get("price")),
                duration=_clean_str(raw.get("duration")),
                frequency=_clean_str(raw.get("frequency")),
                hours=_clean_str(raw.get("hours")),
                source_url=sources[0] if sources else None,
            )
        )
    return items


def curate_local_transport(
    destination: str, country: str | None = None
) -> LocalTransportPlan | None:
    """공항↔시내 교통 + 교통패스를 웹검색으로 종합한다(정적 데이터 없는 도시 폴백).

    특정 출발 시각은 만들지 말고(요금·간격·운영시간 같은 일반 정보만), 근거 URL을 붙인다.
    비활성/실패/항목 없음이면 None.
    """
    settings = get_settings()
    if not _enabled(settings):
        return None
    cache_key = destination.strip().lower()
    where = f"{destination}({country})" if country else destination

    prompt = (
        "너는 한국인 여행자를 위한 현지 교통 큐레이터다. live web search로 공식 교통공사·공항·"
        "관광청과 한국어 여행 블로그를 검색해 "
        f"'{where}'의 **공항↔시내 이동수단**과 **교통패스/교통카드**를 종합하라.\n"
        f"{source_hints_block(destination)}\n"
        "공항 이동은 각 수단의 대략 요금·소요시간·배차간격(frequency)·운영시간(hours)을 적되, "
        "특정 출발 시각은 지어내지 마라(일반 정보만). 교통패스는 카드명·대략 요금·혜택을 적어라. "
        "각 항목에 근거 URL을 최소 1개. 실제 존재하는 것만, 지어내지 마라.\n\n"
        "출력은 설명·코드펜스 없이 아래 JSON 객체 하나만:\n"
        "{\n"
        f'  "city": "{destination}",\n'
        '  "summary": "현지 교통 한두 문장 요약",\n'
        '  "airport_transfers": [{"name":"히드로 익스프레스","detail":"패딩턴역까지 직통",'
        '"price":"약 25파운드","duration":"약 15분","frequency":"15분 간격",'
        '"hours":"05:00~24:00","sources":["url"]}],\n'
        '  "transit_passes": [{"name":"오이스터 카드","detail":"지하철·버스 충전식",'
        '"price":"보증금 7파운드","sources":["url"]}],\n'
        '  "tips": ["현지 교통 팁 1~3개"]\n'
        "}\n"
        "공항 이동 2~4개, 교통패스 1~3개."
    )

    def compute() -> LocalTransportPlan | None:
        data = _run(prompt, settings)
        if not isinstance(data, dict):
            return None
        transfers = _transport_items(data.get("airport_transfers"), "airport")
        passes = _transport_items(data.get("transit_passes"), "pass")
        if not transfers and not passes:
            return None
        city = _clean_str(data.get("city")) or destination
        summary = _clean_str(data.get("summary")) or f"{city} 현지 교통 안내"
        src = next(
            (i.source_url for i in [*transfers, *passes] if i.source_url),
            _maps_url(city, destination),
        )
        return LocalTransportPlan(
            city=city,
            summary=summary,
            airport_transfers=transfers,
            transit_passes=passes,
            tips=_clean_list(data.get("tips")),
            source_url=src,
            metadata=_llm_metadata(src),
        )

    return _cached(_LOCALTRANS_CACHE, cache_key, compute)


def recommend_destinations(
    hint: str, interests: list[str] | None = None, count: int = 3
) -> list[str] | None:
    """모호한 여행 의도(hint)에 맞는 실제 해외 도시를 웹검색으로 추천한다(한국인 기준).

    예: '일본 온천'→하코네·벳푸·유후인, '따뜻한 휴양지'→다낭·세부·푸켓, '유럽 배낭여행'→
    프라하·부다페스트·빈. 도시를 콕 집지 않은 질의(분위기·테마·지역)를 구체 도시로 바꾼다.
    비활성/실패면 None → 호출부가 기존 기본값으로 폴백.
    """
    settings = get_settings()
    if not _enabled(settings) or not hint.strip():
        return None
    cache_key = f"{hint.strip().lower()}|{','.join(interests or [])}|{count}"
    want = max(1, count)
    interest_line = f"여행자 관심사: {', '.join(i for i in interests if i)}\n" if interests else ""
    prompt = (
        "너는 한국인 해외여행 큐레이터다. live web search로 아래 '여행 의도'에 가장 잘 맞는 실제 "
        "해외 여행도시를 추천하라(한국에서 항공으로 가기 좋은 곳 우선). 의도가 분위기·테마"
        "(온천·휴양·야경·미식 등)나 지역(유럽·동남아 등)이면 그에 맞는 구체적인 '도시'를 골라라"
        "(국가·지역명 말고 도시). 실제 존재하는 도시만, 한국어 도시명으로.\n"
        f"여행 의도: {hint}\n"
        f"{interest_line}"
        "출력은 설명·코드펜스 없이 JSON 하나만:\n"
        '{"cities": ["도시명", ...]}\n'
        f"가장 적합한 도시 {want}곳만, 첫 번째가 가장 추천."
    )

    def compute() -> list[str] | None:
        data = _run(prompt, settings)
        if not isinstance(data, dict):
            return None
        cities = [
            c.strip()
            for c in (data.get("cities") or [])
            if isinstance(c, str) and c.strip()
        ]
        return cities[:want] or None

    return _cached(_RECOMMEND_CACHE, cache_key, compute)


def curate_stay_areas(destination: str) -> StayAreaGuide | None:
    """'어느 동네에 묵을지'를 웹검색으로 종합 추천한다. 비활성/실패 시 None."""
    settings = get_settings()
    if not _enabled(settings):
        return None
    cache_key = destination.strip().lower()

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
    def compute() -> StayAreaGuide | None:
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
        return StayAreaGuide(
            destination=destination,
            summary=summary,
            areas=areas,
            source_url=first_source,
            metadata=_llm_metadata(first_source or _maps_url(destination, destination)),
        )

    return _cached(_STAY_CACHE, cache_key, compute)


def curate_companion_cities(destination: str, days_count: int) -> list[CompanionCity]:
    """그 도시 여행에서 대다수가 함께 묶는 '핵심 동반 도시'를 웹검색으로 판단한다.

    단순 근교 명소가 아니라 그 자체가 목적지급인 도시(예: 오사카↔교토·나라)만. 전철 1시간
    이내로 당일/1박이 현실적인 곳. 비활성/짧은 일정(3일 미만)/없음이면 빈 리스트 → 단일 도시.
    """
    settings = get_settings()
    if not _enabled(settings) or days_count < 3:
        return []
    cache_key = f"{destination.strip().lower()}|{days_count}"
    with _CACHE_LOCK:
        if cache_key in _COMPANION_CACHE:
            return _COMPANION_CACHE[cache_key]

    # 본거지가 일정의 과반이 되도록 동반 도시 일수 합을 제한(4일→1, 7일→2, 10일→3).
    cap = max(1, (days_count - 1) // 3)
    prompt = (
        "너는 한국인 여행자를 위한 동선 전문가다. live web search로 실제 여행 후기·추천 일정"
        "(네이버 블로그·카페, 여행 커뮤니티)을 검색해 판단하라.\n"
        f"'{destination}' {days_count}일 여행에서, 대다수 여행자가 사실상 함께 묶어 가는 "
        "'별개의 핵심 도시'가 있는가?\n"
        "● 포함 기준: 행정적으로 독립된 다른 도시이고, 자체 구시가·번화가·볼거리가 있어 보통 "
        "하루를 온전히 쓰는 곳. 전철·기차로 대략 1시간 내라 당일치기나 1박이 현실적. "
        "(예: 오사카↔교토, 홍콩↔마카오, 다낭↔호이안, 니스↔모나코, 비엔나↔브라티슬라바)\n"
        "● 절대 제외: ① 같은 도시·같은 광역권의 구·동네·교외·위성지역"
        "(예: 발리의 우붓, 세부의 라푸라푸, LA의 애너하임 — 이건 같은 목적지 '안'이다). "
        "② 단일 명소·자연경관·테마파크·궁전·유적(예: 베르사유 궁전, 그랜드캐니언, 디즈니랜드 "
        "— 이런 건 도시가 아니라 '근교 명소'라 여기서 빼고 따로 다룬다).\n"
        f"{source_hints_block(destination)}\n"
        "각 도시에 보통 며칠 배분하는지, 왜 함께 가는지, 근거 출처 URL을 붙여라. "
        f"동반 도시는 1곳을 우선(일정이 길 때만 최대 2곳), 일수 합은 {cap}일 이하 — 본거지"
        f"({destination})가 일정의 과반이어야 한다. 애매하면 넣지 말고 빈 배열로 둬라.\n\n"
        "출력은 설명·코드펜스 없이 아래 JSON 객체 하나만:\n"
        "{\n"
        '  "companions": [{"city":"교토", "days":1, '
        '"reason":"오사카에서 전철 15분, 90% 이상 함께 방문", "source_url":"url"}]\n'
        "}\n"
        "함께 가는 비중이 높은 순."
    )
    data = _run(prompt, settings)
    if not isinstance(data, dict):
        return []
    raw = data.get("companions")
    if not isinstance(raw, list):
        return []
    companions: list[CompanionCity] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        city = item.get("city")
        source_url = _clean_str(item.get("source_url"))
        # 근거 없는 추천은 버린다(같은 도시·본거지 중복도 제외).
        if not isinstance(city, str) or not city.strip() or not source_url:
            continue
        if city.strip().lower() == destination.strip().lower():
            continue
        companions.append(
            CompanionCity(
                city=city.strip(),
                days=_coerce_nights(item.get("days"), 1),
                reason=(item.get("reason") or "").strip(),
                source_url=source_url,
            )
        )
    result = companions[:2]
    with _CACHE_LOCK:
        _COMPANION_CACHE[cache_key] = result
    return result


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

    prompt = (
        "너는 한국인 여행자를 위한 현지 큐레이터다. live web search로 관광청·공식 행사 페이지, "
        "지역 뉴스, 네이버 블로그·카페를 검색해 "
        f"'{destination}'에서 열리는 축제·전시·콘서트·시장·스포츠 등 여행자가 갈 만한 행사를 "
        f"정리하라. {when}\n"
        f"{source_hints_block(destination)}\n"
        "반드시 실제로 그 시기에 열리는 행사만 적고, 각 행사에 근거 출처 URL을 붙여라. "
        "출처를 못 찾거나 그 기간에 열리는지 불확실하면 빼라(지어내지 마라). "
        "해당 기간에 특별한 행사가 없으면 events를 빈 배열로 둬라.\n"
        "name·venue는 한국어(한글)로, 검색용 원어명은 괄호 병기"
        "(예: 기온 마쓰리(祇園祭), 야사카 신사(八坂神社)).\n\n"
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
    def compute() -> LocalEventsGuide | None:
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
        return LocalEventsGuide(
            destination=destination,
            date_range=date_label,
            summary=summary,
            events=events,
            source_url=first_source,
            metadata=_llm_metadata(first_source or _maps_url(destination, destination)),
        )

    return _cached(_EVENTS_CACHE, cache_key, compute)


def curate_checklist(destination: str, *, context: str) -> PrepChecklist | None:
    """출발 전 준비물·할 일 체크리스트를 LLM이 정리한다. 비활성/실패 시 None.

    전압/플러그·유심·환전 등은 안정적 지식이라 웹검색 없이 추론한다(빠름). 비자·날씨 같은
    여행별 사실은 호출부가 context로 넘긴다.
    """
    settings = get_settings()
    if not _enabled(settings):
        return None
    cache_key = f"{destination.strip().lower()}|{context}"

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
    def compute() -> PrepChecklist | None:
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
        return PrepChecklist(
            destination=destination,
            summary=summary,
            groups=groups,
            metadata=_llm_metadata(_maps_url(destination, destination)),
        )

    return _cached(_CHECK_CACHE, cache_key, compute)


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
    def compute() -> MultiCityPlan | None:
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
        return MultiCityPlan(
            destinations=destinations,
            summary=(data.get("summary") or f"{cities} 멀티시티 동선").strip(),
            segments=segments,
            legs=legs,
            tips=_clean_list(data.get("tips")),
            metadata=_llm_metadata(_maps_url(destinations[0], destinations[0])),
        )

    return _cached(_MULTICITY_CACHE, cache_key, compute)
