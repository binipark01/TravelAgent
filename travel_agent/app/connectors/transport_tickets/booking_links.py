"""교통권 예매·라우팅 딥링크 생성.

딥리서치(검증)에 따라 스크래핑은 하지 않고(주요 플랫폼 ToS가 금지) 딥링크만 만든다:
- 구글맵스 대중교통 경로: 키 불필요, 출발/도착 자동 채움(공식 문서로 검증된 포맷).
- Rome2Rio: 전세계 멀티모달 비교(사이트 경로형 URL).
- 지역 공식/대표 예매 플랫폼: 한국 Korail, 대만 THSR, 동남아 12Go, 유럽 Omio/Trainline, 미국 Amtrak.
- 교통패스: JR/유레일/THSR/Korail 패스 — 손익분기는 단정하지 않고 '현재 요금 비교' 안내.
목적지→국가 정규화는 비자 커넥터를 재사용한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import quote, urlencode

from travel_agent.app.connectors.visa.entry_requirements import resolve_country
from travel_agent.app.schemas.common import SourceRef
from travel_agent.app.schemas.providers import (
    BookingPlatform,
    PassSuggestion,
    ProviderMetadata,
    RouteLink,
    TransportTicketGuide,
)
from travel_agent.app.utils.ids import new_id
from travel_agent.app.utils.time import expires_in, utc_now


def maps_transit_url(origin: str, destination: str) -> str:
    """구글맵스 대중교통 경로 딥링크(키 불필요, 공식 Maps URLs 포맷)."""
    params = urlencode(
        {"api": "1", "origin": origin, "destination": destination, "travelmode": "transit"}
    )
    return f"https://www.google.com/maps/dir/?{params}"


def rome2rio_url(origin: str, destination: str) -> str:
    """Rome2Rio 멀티모달 비교 페이지(경로형 URL)."""
    return f"https://www.rome2rio.com/s/{quote(origin)}/{quote(destination)}"


@dataclass(frozen=True)
class _Platform:
    name: str
    url: str
    covers: str
    note: str | None = None


@dataclass(frozen=True)
class _Region:
    platforms: list[_Platform] = field(default_factory=list)
    pass_name: str | None = None
    pass_url: str | None = None
    pass_note: str | None = None


# 전세계 공통 fallback(어느 지역이든 동작).
_GLOBAL = _Platform(
    "Rome2Rio", "https://www.rome2rio.com/", "기차·버스·페리·항공 멀티모달 비교",
    "전세계 A→B 이동 수단·소요시간 비교",
)

# 국가별 대표 예매 플랫폼 + 교통패스(딥리서치 검증/공식 페이지 기준).
_REGIONS: dict[str, _Region] = {
    "일본": _Region(
        [
            _Platform("12Go", "https://12go.asia/", "기차·버스·페리", "동아시아 광역 예매"),
            _Platform("Klook", "https://www.klook.com/", "패스·공항픽업·티켓", "패스·액티비티"),
        ],
        "JR 패스 / 지역 레일패스",
        "https://www.japanrailpass.net/",
        "여러 도시·장거리 이동이 있으면 유리할 수 있어요. 지역패스(홋카이도/간사이)도 비교하세요.",
    ),
    "태국": _Region(
        [_Platform("12Go Asia", "https://12go.asia/", "기차·버스·페리·밴", "동남아 1위")]
    ),
    "베트남": _Region(
        [_Platform("12Go Asia", "https://12go.asia/", "기차·버스·페리", "동남아 광역")]
    ),
    "말레이시아": _Region(
        [_Platform("12Go Asia", "https://12go.asia/", "기차·버스·페리", "동남아 광역")]
    ),
    "싱가포르": _Region(
        [_Platform("12Go Asia", "https://12go.asia/", "기차·버스·페리", "동남아 광역")]
    ),
    "인도네시아": _Region(
        [_Platform("12Go Asia", "https://12go.asia/", "기차·버스·페리", "동남아 광역")]
    ),
    "필리핀": _Region(
        [_Platform("12Go Asia", "https://12go.asia/", "페리·버스", "도서 간 페리")]
    ),
    "한국": _Region(
        [_Platform("Korail(공식)", "https://www.korail.com/global/eng/main", "KTX·일반열차",
                   "외국인 영문 예매")],
        "코레일 패스",
        "https://www.letskorail.com/",
        "여러 도시를 기차로 다니면 코레일 패스를 비교하세요.",
    ),
    "대만": _Region(
        [_Platform("THSR 고속철(공식)", "https://irs.thsrc.com.tw/IMINT/?locale=en", "고속철도",
                   "영문 예매·결제")],
        "THSR 패스",
        "https://pass.thsrc.com.tw/",
        "남북 종단(타이베이↔가오슝)이 잦으면 THSR 패스를 비교하세요.",
    ),
    "유럽(셰겐)": _Region(
        [
            _Platform("Omio", "https://www.omio.com/", "기차·버스·항공", "유럽 광역 비교·예매"),
            _Platform("Trainline", "https://www.thetrainline.com/", "기차·버스", "유럽 철도 예매"),
        ],
        "유레일(Eurail) 패스",
        "https://www.eurail.com/",
        "여러 나라를 기차로 이동하면 유레일을 비교하세요. 사전 구매 개별권이 더 쌀 때도 많습니다.",
    ),
    "영국": _Region(
        [_Platform("Trainline", "https://www.thetrainline.com/", "기차·버스", "영국 철도 예매")],
    ),
    "미국": _Region(
        [
            _Platform("Amtrak", "https://www.amtrak.com/", "기차", "장거리 철도"),
            _Platform("Wanderu", "https://www.wanderu.com/", "버스·기차", "버스·기차 비교"),
        ],
    ),
    "중국": _Region(
        [_Platform("Trip.com", "https://www.trip.com/trains/", "고속철·기차", "중국 철도 예매")]
    ),
    "홍콩": _Region(
        [_Platform("Klook", "https://www.klook.com/", "MTR·공항특급·티켓", "교통패스·티켓")]
    ),
    "호주": _Region(
        [_Platform("Rome2Rio", "https://www.rome2rio.com/", "기차·버스·페리", "도시간 비교")]
    ),
    "캐나다": _Region(
        [_Platform("VIA Rail", "https://www.viarail.ca/", "기차", "캐나다 철도")],
    ),
}


def _metadata() -> ProviderMetadata:
    now = utc_now()
    source_ref = SourceRef(
        source_id=new_id("src"),
        provider="transport_tickets",
        source_url="https://www.google.com/maps",
        title="교통권 예매·경로 딥링크",
        reference=f"tickets-{now.strftime('%Y%m%d')}",
        retrieved_at=now,
        expires_at=expires_in(24 * 30),
        is_live=False,
        is_mock=False,
        source_type="deep_link",
        confidence=0.6,
        freshness_note="딥링크 모음(스크래핑 없음). 요금·시간표는 각 사이트에서 확인.",
    )
    return ProviderMetadata(
        provider_name="transport_tickets",
        retrieved_at=now,
        source_ref=source_ref,
        expires_at=expires_in(24 * 30),
        normalized_currency=None,
        is_mock=False,
    )


def build_transport_tickets(
    destination: str,
    *,
    hub_city: str | None = None,
    airport_label: str | None = None,
    nearby: list[str] | None = None,
    hub_lat: float | None = None,
    hub_lng: float | None = None,
) -> TransportTicketGuide | None:
    """목적지 기준 교통권 플랫폼·패스·구간 경로 딥링크를 만든다."""
    country = resolve_country(destination)
    hub = hub_city or destination.split(",")[0].strip()
    region = _REGIONS.get(country) if country else None

    platforms = [
        BookingPlatform(name=p.name, url=p.url, covers=p.covers, note=p.note)
        for p in (region.platforms if region else [])
    ]
    # 전세계 멀티모달 비교는 항상 하나 추가(겹치지 않을 때만).
    if all(p.name != _GLOBAL.name for p in platforms):
        platforms.append(
            BookingPlatform(name=_GLOBAL.name, url=_GLOBAL.url, covers=_GLOBAL.covers,
                            note=_GLOBAL.note)
        )

    pass_suggestion = None
    if region and region.pass_name and region.pass_url:
        pass_suggestion = PassSuggestion(
            name=region.pass_name, url=region.pass_url, note=region.pass_note or "",
        )

    route_links: list[RouteLink] = []
    if airport_label:
        route_links.append(
            RouteLink(
                label=f"{airport_label} → {hub} 시내",
                maps_url=maps_transit_url(airport_label, f"{hub}역"),
            )
        )
    for spot in (nearby or [])[:6]:
        route_links.append(
            RouteLink(
                label=f"{hub} → {spot}",
                maps_url=maps_transit_url(hub, spot),
                booking_url=rome2rio_url(hub, spot),
            )
        )

    summary = (
        f"{hub} 이동은 구글맵스로 경로를 확인하고, 예매는 아래 플랫폼을 이용하세요."
        if not pass_suggestion
        else f"{hub} 권역은 교통패스도 고려해볼 만합니다. 구간 경로와 예매처를 정리했어요."
    )
    return TransportTicketGuide(
        destination_country=country or hub,
        summary=summary,
        hub=hub,
        hub_lat=hub_lat,
        hub_lng=hub_lng,
        platforms=platforms,
        pass_suggestion=pass_suggestion,
        route_links=route_links,
        metadata=_metadata(),
    )
