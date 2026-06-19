from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from urllib.parse import quote_plus

from travel_agent.app.llm import geo_resolver
from travel_agent.app.schemas.brief import TripBrief


@dataclass(frozen=True, slots=True)
class FlightSearchLinks:
    origin_label: str
    destination_label: str
    departure_date: date
    return_date: date | None
    naver_url: str
    skyscanner_url: str
    google_url: str
    # 목적지에 국제선 직항이 적어 인근 허브로 검색할 때의 안내(예: 시즈오카→나고야).
    note: str | None = None

    def summary(self) -> str:
        date_range = self.departure_date.isoformat()
        if self.return_date:
            date_range = f"{date_range} ~ {self.return_date.isoformat()}"
        return f"항공 검색: {self.origin_label} -> {self.destination_label}, {date_range}"


@dataclass(frozen=True, slots=True)
class AirportRoute:
    origin_iata: str
    origin_skyscanner: str
    destination_iata: str
    destination_skyscanner: str


# 정규화된 도시명 -> (IATA, skyscanner 코드).
# LLM이 출발/목적지를 영어·한글·국가병기(예: "Seoul, South Korea")로 줄 수 있어
# 별칭을 폭넓게 매핑한다.
# (IATA, skyscanner 코드) -> 별칭들. LLM이 도시명(한/영)·공항코드·국가명 무엇으로 줘도
# 매핑되게 별칭을 폭넓게 등록한다. 네이버는 메트로코드(TYO/OSA)로는 결과가 없어
# 대표 공항코드(NRT/KIX)를 쓴다. 영문/코드 별칭은 소문자로 적는다(_normalize_place가 소문자화).
_AIRPORT_ALIASES: list[tuple[tuple[str, str], tuple[str, ...]]] = [
    (
        ("ICN", "sel"),
        (
            "서울", "seoul", "인천", "incheon", "김포", "gimpo",
            "icn", "gmp", "sel",
            "대한민국", "한국", "korea", "south korea", "republic of korea",
        ),
    ),
    # 일본
    (("CTS", "cts"), ("삿포로", "sapporo", "신치토세", "cts")),
    (
        ("NRT", "tyo"),
        ("도쿄", "동경", "tokyo", "나리타", "narita", "하네다", "haneda", "nrt", "hnd", "tyo"),
    ),
    (("KIX", "osa"), ("오사카", "osaka", "교토", "kyoto", "고베", "kobe", "kix", "itm", "osa")),
    (("FUK", "fuk"), ("후쿠오카", "fukuoka", "fuk")),
    (("NGO", "ngo"), ("나고야", "nagoya", "ngo")),
    (("OKA", "oka"), ("오키나와", "okinawa", "나하", "naha", "oka")),
    # 동아시아
    (("TPE", "tpe"), ("타이베이", "타이페이", "taipei", "대만", "taiwan", "tpe")),
    (("HKG", "hkg"), ("홍콩", "hong kong", "hongkong", "hkg")),
    (("MFM", "mfm"), ("마카오", "macau", "macao", "mfm")),
    (("PVG", "sha"), ("상하이", "상해", "shanghai", "pvg", "sha")),
    (("PEK", "bjs"), ("베이징", "북경", "beijing", "pek", "pkx", "bjs")),
    (("TAO", "tao"), ("칭다오", "청도", "qingdao", "tao")),
    # 동남아
    (("BKK", "bkk"), ("방콕", "bangkok", "태국", "thailand", "bkk")),
    (("HKT", "hkt"), ("푸켓", "phuket", "hkt")),
    (("DAD", "dad"), ("다낭", "danang", "da nang", "dad")),
    (("HAN", "han"), ("하노이", "hanoi", "han")),
    (("SGN", "sgn"), ("호치민", "ho chi minh", "사이공", "saigon", "sgn")),
    (("SIN", "sin"), ("싱가포르", "singapore", "sin")),
    (("KUL", "kul"), ("쿠알라룸푸르", "kuala lumpur", "말레이시아", "malaysia", "kul")),
    (("BKI", "bki"), ("코타키나발루", "kota kinabalu", "코타 키나발루", "bki")),
    (("CEB", "ceb"), ("세부", "cebu", "ceb")),
    (("MNL", "mnl"), ("마닐라", "manila", "mnl")),
    (("DPS", "dps"), ("발리", "bali", "덴파사르", "denpasar", "dps")),
    # 미주/태평양
    (("GUM", "gum"), ("괌", "guam", "gum")),
    (("SPN", "spn"), ("사이판", "saipan", "spn")),
    # 장거리(참고용 링크 위주)
    (("CDG", "cdg"), ("파리", "paris", "cdg")),
    (("LHR", "lon"), ("런던", "london", "lhr")),
    (("FCO", "rom"), ("로마", "rome", "fco")),
    (("JFK", "nyc"), ("뉴욕", "new york", "jfk", "nyc")),
    (("FRA", "fra"), ("프랑크푸르트", "frankfurt", "fra")),
    # 국내선
    (("CJU", "cju"), ("제주", "jeju", "cju")),
    (("PUS", "pus"), ("부산", "busan", "pus")),
]
AIRPORT_CODES: dict[str, tuple[str, str]] = {}
for _codes, _aliases in _AIRPORT_ALIASES:
    for _alias in _aliases:
        AIRPORT_CODES[_alias] = _codes

# 도시명 끝에 붙는 국가/지역 표기를 제거한다.
_PLACE_SUFFIXES = (
    ", japan",
    ", south korea",
    ", korea",
    " japan",
    " 일본",
    " 특별시",
)


def _normalize_place(name: str) -> str:
    normalized = name.strip().lower()
    # "Bangkok, Thailand"처럼 콤마로 국가/지역을 병기한 경우 도시명만 남긴다.
    normalized = normalized.split(",")[0].strip()
    for suffix in _PLACE_SUFFIXES:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].strip(" ,")
    return normalized


def _codes_for(name: str) -> tuple[str, str] | None:
    codes = AIRPORT_CODES.get(_normalize_place(name))
    if codes:
        return codes
    # 카탈로그에 없는 도시(시즈오카 등)는 LLM이 IATA·스카이스캐너 코드를 해석한다.
    # (라이브 LLM이 꺼져 있으면 resolve_place가 None → 기존처럼 None을 돌려준다.)
    resolved = geo_resolver.resolve_place(name)
    if resolved and resolved.iata:
        return (resolved.iata, resolved.skyscanner or resolved.iata.lower())
    return None


def build_flight_search_links(brief: TripBrief) -> FlightSearchLinks | None:
    if not brief.origin or not brief.destinations or not brief.start_date:
        return None
    destination = brief.selected_destination or brief.destinations[0]
    route = _airport_route(brief.origin, destination)
    if not route:
        return None
    return_date = brief.end_date
    # 목적지가 LLM으로 해석된 경우, 인근 허브 안내(직항 적음 등)를 함께 싣는다(캐시 적중).
    resolved = geo_resolver.resolve_place(destination)
    return FlightSearchLinks(
        origin_label=brief.origin,
        destination_label=destination,
        departure_date=brief.start_date,
        return_date=return_date,
        naver_url=_naver_url(route, brief.start_date, return_date, brief.travelers or 1),
        skyscanner_url=_skyscanner_url(
            route, brief.start_date, return_date, brief.travelers or 1
        ),
        google_url=_google_url(brief.origin, destination, brief.start_date, return_date),
        note=resolved.hub_note if resolved else None,
    )


def _airport_route(origin: str, destination: str) -> AirportRoute | None:
    origin_codes = _codes_for(origin)
    destination_codes = _codes_for(destination)
    if not origin_codes or not destination_codes:
        return None
    return AirportRoute(
        origin_iata=origin_codes[0],
        origin_skyscanner=origin_codes[1],
        destination_iata=destination_codes[0],
        destination_skyscanner=destination_codes[1],
    )


def _compact_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def _short_date(value: date) -> str:
    return value.strftime("%y%m%d")


def _naver_url(route: AirportRoute, departure: date, return_date: date | None, adults: int) -> str:
    outbound = f"{route.origin_iata}-{route.destination_iata}-{_compact_date(departure)}"
    if not return_date:
        return (
            "https://flight.naver.com/flights/international/"
            f"{outbound}?adult={adults}&fareType=Y"
        )
    inbound = f"{route.destination_iata}-{route.origin_iata}-{_compact_date(return_date)}"
    return (
        "https://flight.naver.com/flights/international/"
        f"{outbound}/{inbound}?adult={adults}&fareType=Y"
    )


def _skyscanner_url(
    route: AirportRoute, departure: date, return_date: date | None, adults: int
) -> str:
    base = (
        "https://www.skyscanner.co.kr/transport/flights/"
        f"{route.origin_skyscanner}/{route.destination_skyscanner}/{_short_date(departure)}"
    )
    if return_date:
        base = f"{base}/{_short_date(return_date)}"
    return (
        f"{base}/?adultsv2={adults}&cabinclass=economy&childrenv2="
        "&inboundaltsenabled=false&outboundaltsenabled=false&preferdirects=false"
    )


def _google_url(origin: str, destination: str, departure: date, return_date: date | None) -> str:
    query = f"Flights from {origin} to {destination} {departure.isoformat()}"
    if return_date:
        query = f"{query} return {return_date.isoformat()}"
    return f"https://www.google.com/travel/flights?q={quote_plus(query)}"
