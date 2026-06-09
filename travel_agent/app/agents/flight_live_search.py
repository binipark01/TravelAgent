"""네이버·구글 항공편 화면을 브라우저로 분석해 실제 FlightOption을 만든다.

`build_flight_search_links`로 소스별 검색 URL을 만들고, 한 브라우저로 페이지들을
렌더링해 실제 운임 후보를 추출한 뒤 FlightOption으로 변환한다. 네이버는 가는/오는 편을
모두 주고, 구글은 가는 편+왕복 총액을 준다(오는 편 시각은 예약 화면에서 확인).
경로/날짜를 만들 수 없거나 추출이 실패하면 빈 목록을 반환한다.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from travel_agent.app.connectors.flights.google_browser import parse_google_flight_text
from travel_agent.app.connectors.flights.naver_browser import (
    NaverBrowserExtractionError,
    NaverFlightBrowserExtractor,
    parse_naver_flight_text,
)
from travel_agent.app.llm.flight_search_links import FlightSearchLinks, build_flight_search_links
from travel_agent.app.schemas.brief import TripBrief
from travel_agent.app.schemas.common import Money, SourceRef
from travel_agent.app.schemas.llm import FlightFareCandidate
from travel_agent.app.schemas.providers import FlightOption, ProviderMetadata
from travel_agent.app.utils.ids import new_id
from travel_agent.app.utils.time import expires_in, utc_now

_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")
# 네이버 화면의 UI 텍스트가 항공사명으로 잘못 추출되는 경우를 걸러낸다.
_AIRLINE_NOISE = ("그래프", "변동", "추이", "차트", "가격대", "필터")


def extract_live_flight_options(
    brief: TripBrief,
    *,
    currency: str,
    timeout_seconds: int = 40,
    limit: int = 5,
    max_date_searches: int = 6,
    request_text: str | None = None,
) -> list[FlightOption]:
    """유연 날짜 범위(window) 안의 출발일을 전부 검색한 뒤 좋은 후보를 추려서 정리한다.

    범위가 여행 길이(N박)와 같으면 단일 검색, 더 넓으면 윈도우 안의 모든 출발일을
    병렬 검색한다. 모은 뒤 요청한 시간대 조건(오전출발·오후귀국)과 가격을 함께 보고
    `_curate`로 순위를 매겨 반환한다.
    """
    window_start = brief.start_date
    if window_start is None:
        return []
    nights = brief.duration_nights
    if nights is None and brief.end_date is not None:
        nights = max((brief.end_date - window_start).days, 1)
    if not nights or nights < 1:
        nights = 4

    window_start, window_end = _search_window(brief, nights, request_text)
    departures = _candidate_departures(window_start, window_end, nights, max_date_searches)
    per_search_limit = max(limit, 5)

    # 날짜별로 네이버+구글 검색 URL을 모아 브라우저 하나로 한 번에 처리한다(CPU 절감).
    jobs: list[tuple[str, FlightSearchLinks, str]] = []  # (url, links, source)
    for departure in departures:
        search_brief = brief.model_copy(
            update={"start_date": departure, "end_date": departure + timedelta(days=nights)}
        )
        links = build_flight_search_links(search_brief)
        if links is None:
            continue
        jobs.append((links.naver_url, links, "naver_flight"))
        if links.google_url:
            jobs.append((links.google_url, links, "google_flights"))
    if not jobs:
        return []

    try:
        pages = NaverFlightBrowserExtractor(timeout_seconds=timeout_seconds).fetch_pages(
            [url for url, _, _ in jobs]
        )
    except NaverBrowserExtractionError:
        return []

    options: list[FlightOption] = []
    for (url, links, source), page in zip(jobs, pages, strict=False):
        if not page.text:
            continue
        source_url = page.final_url or page.url or url
        if source == "google_flights":
            candidates = parse_google_flight_text(
                text=page.text, source_url=source_url, limit=per_search_limit
            )
        else:
            candidates = parse_naver_flight_text(
                text=page.text, source_url=source_url, limit=per_search_limit
            )
        for candidate in candidates:
            option = flight_candidate_to_option(candidate, links, currency)
            if option is not None:
                options.append(option)

    options = _dedupe(options)
    return _curate(
        options,
        brief,
        limit,
        direct_only=_direct_requested(request_text),
        flight_cap=_flight_price_cap(request_text),
        airline=_preferred_airline(request_text),
    )


def _search_window(
    brief: TripBrief, nights: int, request_text: str | None = None
) -> tuple[date, date | None]:
    """검색할 날짜 윈도우(start, end)를 정한다.

    사용자가 정확한 날짜를 안 주고 일정이 유연하면(flexible_dates) 출발일이 한 날짜로
    좁혀져 있어도 ±3일을 검색 대상으로 넓혀 여러 날짜를 비교하게 한다. 정확한 날짜를
    준 경우(flexible_dates=False)엔 그대로 두어 단일 날짜만 검색한다.
    """
    start = brief.start_date
    end = brief.end_date
    span = (end - start).days if end else 0
    if brief.flexible_dates and span <= nights:
        # 제약 방향을 보고 펼친다.
        #  - "10일 이전/까지"(상한): 정한 날짜 이후로 안 가게 뒤로 펼친다.
        #  - "6일 이후/부터"(하한) 또는 모호: 정한 날짜 이전으로 안 가게 앞으로 펼친다.
        if _constraint_direction(request_text) == "before":
            start = start - timedelta(days=6)
        end = start + timedelta(days=6 + nights)
    return start, end


def _is_direct(option: FlightOption) -> bool:
    return any("경유: 직항" in note for note in option.notes)


_KNOWN_AIRLINES = (
    "대한항공", "아시아나항공", "아시아나", "진에어", "제주항공", "티웨이항공", "티웨이",
    "에어부산", "에어서울", "이스타항공", "이스타", "에어로케이", "에어프레미아",
    "피치항공", "피치", "스쿠트", "전일본공수", "일본항공", "산동항공", "파라타항공",
)


def _preferred_airline(text: str | None) -> str | None:
    """'대한항공으로' 같은 항공사 지정 감지. 부정 표현('말고')은 무시."""
    if not text:
        return None
    if any(neg in text for neg in ("말고", "제외", "빼고", "말구")):
        return None
    for name in _KNOWN_AIRLINES:
        if name in text:
            return name
    return None


def _direct_requested(text: str | None) -> bool:
    """'직항만/직항으로' 같은 직항 요청 감지(경유 무관 표현은 제외)."""
    if not text:
        return False
    lowered = text.lower()
    if any(k in lowered for k in ("경유 상관", "경유도", "경유 무관", "경유 괜찮")):
        return False
    return any(k in lowered for k in ("직항", "직행", "nonstop", "non-stop", "direct"))


def _flight_price_cap(text: str | None) -> int | None:
    """'항공권 40만원 이내' 같은 항공 예산 상한을 원 단위로 돌려준다(없으면 None)."""
    if not text:
        return None
    lowered = text.lower()
    if not any(k in lowered for k in ("항공", "비행기", "flight")):
        return None
    if not any(k in lowered for k in ("이내", "이하", "under", "밑", "안쪽")):
        return None
    match = re.search(r"(\d+)\s*만", text)
    return int(match.group(1)) * 10000 if match else None


def _constraint_direction(text: str | None) -> str | None:
    """요청 문구에서 날짜 제약 방향을 알아낸다. 'before'(이전/까지) / 'after'(이후/부터) / None."""
    if not text:
        return None
    lowered = text.lower()
    after_kw = ("이후", "부터", "이상", "넘어", " after", " from ")
    before_kw = ("이전", "까지", "전에", "이내", "안에", " before", " by ")
    has_after = any(k in lowered for k in after_kw)
    has_before = any(k in lowered for k in before_kw)
    if has_after and has_before:
        return None  # 범위 표현은 윈도우가 처리하므로 한쪽으로 펼치지 않는다
    if has_before:
        return "before"
    if has_after:
        return "after"
    return None


def _candidate_departures(
    window_start: date, window_end: date | None, nights: int, max_searches: int
) -> list[date]:
    """윈도우 안의 출발일 후보를 만든다.

    기본적으로 가능한 모든 출발일(window_start ~ window_end-N박)을 전부 검색 대상에
    넣는다. 후보가 max_searches보다 많으면(=윈도우가 매우 넓으면) 고르게 솎아낸다.
    """
    if window_end is None or (window_end - window_start).days <= nights:
        return [window_start]
    latest = window_end - timedelta(days=nights)
    total_days = (latest - window_start).days
    if total_days <= 0:
        return [window_start]
    all_days = [window_start + timedelta(days=offset) for offset in range(total_days + 1)]
    if len(all_days) <= max_searches:
        return all_days
    step = (len(all_days) - 1) / (max_searches - 1)
    picked: list[date] = []
    for index in range(max_searches):
        day = all_days[round(index * step)]
        if day not in picked:
            picked.append(day)
    return picked


def _curate(
    options: list[FlightOption],
    brief: TripBrief,
    limit: int,
    *,
    direct_only: bool = False,
    flight_cap: int | None = None,
    airline: str | None = None,
) -> list[FlightOption]:
    """검색한 후보를 요청 조건·가격·날짜·소스 다양성을 함께 보고 추려서 정리한다.

    직항만/항공 예산 같은 명시 조건을 먼저 거른 뒤, 날짜가 한쪽으로 쏠리지 않게
    **출발일별 대표 1개씩** 고르고, 소스(네이버·구글)가 한쪽만 나오지 않게 **번갈아**
    담는다. 추천 이유는 notes 맨 앞에 붙인다.
    """
    if not options:
        return []
    # 직항만/항공사/항공 예산 필터(요청 시). 조건 만족 후보가 없으면 원래 풀을 유지한다.
    over_budget_only = False
    airline_unavailable = False
    if direct_only:
        direct = [option for option in options if _is_direct(option)]
        if direct:
            options = direct
    if airline:
        matched = [option for option in options if airline in option.airline]
        if matched:
            options = matched
        else:
            airline_unavailable = True
    if flight_cap:
        within = [option for option in options if (option.price.amount or 0) <= flight_cap]
        if within:
            options = within
        else:
            over_budget_only = True

    # 선호 시간대는 한글/영어 둘 다 인식한다. LLM이 transport_preference나 must_include에
    # "삿포로행 오전 출발, 인천행 오후 출발"처럼 자연어로 넣을 수 있다.
    pref = " ".join([brief.transport_preference or "", *brief.must_include]).lower()
    want_morning = any(token in pref for token in ("morning", "오전", "아침"))
    want_afternoon = any(token in pref for token in ("afternoon", "오후"))

    def sort_key(option: FlightOption) -> tuple[int, float]:
        fit = _schedule_fit(option, want_morning, want_afternoon)
        return (-fit, option.price.amount or 10**12)

    # 소스별로 묶어 각각 날짜 다양화한 뒤, 번갈아(네이버 먼저) 담아 둘 다 노출되게 한다.
    by_provider: dict[str, list[FlightOption]] = {}
    for option in options:
        by_provider.setdefault(option.metadata.source_ref.provider, []).append(option)
    provider_order = sorted(
        by_provider, key=lambda p: (p != "naver_flight", p != "google_flights", p)
    )
    ranked_lists = [_diversify_by_date(by_provider[p], sort_key) for p in provider_order]
    curated = _round_robin(ranked_lists, limit)

    curated.sort(key=sort_key)
    if not curated:
        return []

    cheapest = min(curated, key=lambda option: option.price.amount or 10**12)
    need = (1 if want_morning else 0) + (1 if want_afternoon else 0)
    for option in curated:
        fit = _schedule_fit(option, want_morning, want_afternoon)
        tags: list[str] = []
        if option is cheapest:
            tags.append("💰 추천 중 최저가")
            if over_budget_only and flight_cap:
                tags.append(f"⚠️ {flight_cap // 10000}만원 이내 항공편이 없어 최저가 표시")
            if airline_unavailable and airline:
                tags.append(f"⚠️ '{airline}' 항공편을 찾지 못해 전체 표시")
        if direct_only and _is_direct(option):
            tags.append("직항")
        if want_morning and option.departure_time.hour < 12:
            tags.append("오전 출발")
        if (
            want_afternoon
            and option.return_departure_time is not None
            and option.return_departure_time.hour >= 12
        ):
            tags.append("오후 귀국")
        if need and fit >= need:
            tags.append("✅ 요청한 시간대 조건 충족")
        if tags:
            option.notes.insert(0, " · ".join(tags))
    return curated


def _diversify_by_date(options, sort_key):
    """출발일별 대표 1개씩 앞에 모은 뒤 나머지를 붙여, 날짜가 고르게 퍼지도록 정렬한다."""
    ordered = sorted(options, key=sort_key)
    picked: list[FlightOption] = []
    seen_dates: set[date] = set()
    chosen_ids: set[int] = set()
    for option in ordered:
        day = option.departure_time.date()
        if day not in seen_dates:
            seen_dates.add(day)
            chosen_ids.add(id(option))
            picked.append(option)
    for option in ordered:
        if id(option) not in chosen_ids:
            picked.append(option)
    return picked


def _round_robin(lists: list[list[FlightOption]], limit: int) -> list[FlightOption]:
    """여러 소스 리스트에서 번갈아 뽑아 limit개를 만든다(소스 다양성 보장)."""
    result: list[FlightOption] = []
    chosen_ids: set[int] = set()
    index = 0
    while len(result) < limit and any(index < len(items) for items in lists):
        for items in lists:
            if index < len(items):
                option = items[index]
                if id(option) not in chosen_ids:
                    chosen_ids.add(id(option))
                    result.append(option)
                    if len(result) >= limit:
                        break
        index += 1
    return result


def _schedule_fit(option: FlightOption, want_morning: bool, want_afternoon: bool) -> int:
    fit = 0
    if want_morning and option.departure_time.hour < 12:
        fit += 1
    if (
        want_afternoon
        and option.return_departure_time is not None
        and option.return_departure_time.hour >= 12
    ):
        fit += 1
    return fit


def _dedupe(options: list[FlightOption]) -> list[FlightOption]:
    seen: set[tuple[str, str, str, float]] = set()
    result: list[FlightOption] = []
    for option in options:
        key = (
            option.airline,
            option.departure_time.isoformat(),
            option.return_departure_time.isoformat() if option.return_departure_time else "",
            float(option.price.amount),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(option)
    return result


def flight_candidate_to_option(
    candidate: FlightFareCandidate, links: FlightSearchLinks, currency: str
) -> FlightOption | None:
    airline = (candidate.airline or "").strip()
    if not airline or any(token in airline for token in _AIRLINE_NOISE):
        return None
    departure = _combine(links.departure_date, candidate.outbound_departure)
    arrival = _combine(links.departure_date, candidate.outbound_arrival)
    if departure is None or arrival is None:
        return None
    return_departure = (
        _combine(links.return_date, candidate.inbound_departure) if links.return_date else None
    )
    return_arrival = (
        _combine(links.return_date, candidate.inbound_arrival) if links.return_date else None
    )
    provider = candidate.provider or "naver_flight"
    source_label = _SOURCE_LABELS.get(provider, _SOURCE_LABELS["naver_flight"])
    notes = list(candidate.notes)
    notes.append(f"경유: {candidate.stops or '미확인'}")
    if candidate.outbound_duration:
        notes.append(f"가는 편 소요: {candidate.outbound_duration}")
    if candidate.price:
        notes.append(f"표시 운임: {candidate.price}")
    if return_departure is None and provider == "google_flights":
        notes.append("구글 항공: 가는 편·왕복 총액 기준 (오는 편 시각은 예약 화면에서 확인)")
    notes.append(f"{source_label} 실시간 추출 · 예약 전 재확인 필요")
    return FlightOption(
        option_id=new_id("flt"),
        airline=airline,
        origin=links.origin_label,
        destination=links.destination_label,
        departure_time=departure,
        arrival_time=arrival,
        return_departure_time=return_departure,
        return_arrival_time=return_arrival,
        price=Money(amount=_parse_price(candidate.price), currency=currency),
        refundable=False,
        booking_required=True,
        metadata=_live_metadata(candidate.source_url or links.naver_url, provider),
        notes=notes,
    )


def _combine(value: date | None, label: str | None) -> datetime | None:
    if value is None or not label:
        return None
    match = _TIME_RE.search(label)
    if match is None:
        return None
    return datetime(
        value.year,
        value.month,
        value.day,
        int(match.group(1)),
        int(match.group(2)),
        tzinfo=utc_now().tzinfo,
    )


def _parse_price(price: str | None) -> int:
    digits = re.sub(r"[^\d]", "", price or "")
    return int(digits) if digits else 0


_SOURCE_LABELS = {
    "naver_flight": "네이버 항공권",
    "google_flights": "Google 항공편 검색",
}


def _live_metadata(source_url: str, provider: str = "naver_flight") -> ProviderMetadata:
    now = utc_now()
    label = _SOURCE_LABELS.get(provider, _SOURCE_LABELS["naver_flight"])
    source_ref = SourceRef(
        source_id=new_id("src"),
        provider=provider,
        source_url=source_url,
        title=f"{label} 실시간 검색",
        reference=f"{provider}-{now.strftime('%Y%m%d%H%M%S')}",
        retrieved_at=now,
        expires_at=expires_in(1),
        is_live=True,
        is_mock=False,
        source_type="public_page",
        confidence=0.7,
        freshness_note=f"{label} 화면에서 추출한 실시간 운임. 예약 전 재확인 필요.",
    )
    return ProviderMetadata(
        provider_name=provider,
        retrieved_at=now,
        source_ref=source_ref,
        expires_at=expires_in(1),
        normalized_currency=None,
        is_mock=False,
    )
