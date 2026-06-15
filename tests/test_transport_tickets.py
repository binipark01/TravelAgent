from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from travel_agent.app.connectors.transport_tickets.booking_links import (
    build_transport_tickets,
    maps_transit_url,
    rome2rio_url,
)


def test_maps_transit_url_is_keyless_and_prefilled() -> None:
    url = maps_transit_url("삿포로", "오타루")
    parsed = urlparse(url)
    q = parse_qs(parsed.query)
    assert parsed.netloc == "www.google.com"
    assert "/maps/dir/" in parsed.path
    assert q["api"] == ["1"]  # 키 불필요 포맷
    assert q["travelmode"] == ["transit"]
    assert q["origin"] == ["삿포로"]
    assert q["destination"] == ["오타루"]


def test_rome2rio_url_is_path_based() -> None:
    assert rome2rio_url("Sapporo", "Otaru") == "https://www.rome2rio.com/s/Sapporo/Otaru"


def test_japan_guide_has_jr_pass_and_route_links() -> None:
    guide = build_transport_tickets(
        "Sapporo", hub_city="삿포로", airport_label="삿포로 공항",
        nearby=["오타루", "노보리베츠 온천"],
    )
    assert guide is not None
    assert guide.destination_country == "일본"
    # JR 패스 추천 + 손익분기 단정 없이 비교 안내
    assert guide.pass_suggestion is not None
    assert "패스" in guide.pass_suggestion.name
    # 예매 플랫폼 + 전세계 fallback(Rome2Rio)
    names = [p.name for p in guide.platforms]
    assert any("12Go" in n for n in names)
    assert "Rome2Rio" in names
    # 구간 경로 링크(공항→시내, 허브→근교)
    labels = [r.label for r in guide.route_links]
    assert any("공항" in lbl for lbl in labels)
    assert any("오타루" in lbl for lbl in labels)
    assert all(r.maps_url.startswith("https://www.google.com/maps/dir/") for r in guide.route_links)


def test_taiwan_uses_official_thsr_and_pass() -> None:
    guide = build_transport_tickets("Taipei", hub_city="타이베이")
    assert guide is not None
    assert guide.destination_country == "대만"
    assert any("THSR" in p.name for p in guide.platforms)
    assert guide.pass_suggestion is not None and "THSR" in guide.pass_suggestion.name


def test_unknown_country_falls_back_to_rome2rio() -> None:
    # 데이터 없는 곳도 전세계 fallback(Rome2Rio)은 제공한다.
    guide = build_transport_tickets("Reykjavik", hub_city="Reykjavik")
    assert guide is not None
    assert any(p.name == "Rome2Rio" for p in guide.platforms)
    assert guide.pass_suggestion is None
