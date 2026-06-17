from __future__ import annotations

from travel_agent.app.connectors.flights.naver_browser import parse_naver_flight_text


def test_parse_naver_flight_text_extracts_visible_round_trip_candidates() -> None:
    text = "\n".join(
        [
            "왕복",
            "ICN",
            "CTS",
            "직항만",
            "진에어",
            "08:20ICN",
            "11:00CTS",
            "직항, 02시간 40분",
            "12:10CTS",
            "15:05ICN",
            "직항, 02시간 55분",
            "589,900원~",
            "2만원 할인",
            "왕복 569,900원~",
            "2만원 적립 시",
            "549,900원~",
            "6개 인기 항공편 더보기",
            "대한항공",
            "10:35ICN",
            "13:25CTS",
            "직항, 02시간 50분",
            "14:50CTS",
            "17:55ICN",
            "직항, 03시간 05분",
            "709,100원~",
            "2만원 할인",
            "왕복 689,100원~",
        ]
    )

    options = parse_naver_flight_text(
        text=text,
        source_url="https://flight.naver.com/flights/international/ICN-CTS-20260703/CTS-ICN-20260715",
        limit=3,
    )

    assert len(options) == 2
    assert options[0].airline == "진에어"
    assert options[0].outbound_departure == "08:20 ICN"
    assert options[0].outbound_arrival == "11:00 CTS"
    assert options[0].inbound_departure == "12:10 CTS"
    assert options[0].inbound_arrival == "15:05 ICN"
    # 헤드라인 569,900은 '2만원 할인' 적용가 → 할인 전 일반가 589,900을 잡는다.
    assert options[0].price == "왕복 589,900원~"
    assert options[0].stops == "직항"
    assert options[1].airline == "대한항공"
    assert options[1].price == "왕복 709,100원~"


def test_standard_price_strips_card_event_discount() -> None:
    # 네이버 헤드라인 '왕복 702,600' = 기준가 722,600 - 2만원 카드/이벤트 할인.
    # 일반가(722,600)를 잡아야 한다.
    from travel_agent.app.connectors.flights.naver_browser import (
        _standard_price_before_discount,
        parse_naver_flight_text,
    )

    lines = [
        "진에어", "08:20ICN", "11:00CTS", "직항, 02시간 40분",
        "12:10CTS", "15:05ICN", "직항, 02시간 55분",
        "할인", "성인/하나카드(이용실적 충족시)", "722,600원~",
        "2만원 할인", "왕복 702,600원~", "2만원 적립 시", "682,600원~",
    ]
    pi = lines.index("왕복 702,600원~")
    assert _standard_price_before_discount(lines, 0, pi) == "722,600원~"

    # 할인 패턴이 없으면 헤드라인가를 유지(None).
    clean = ["진에어", "08:20ICN", "11:00CTS", "직항", "12:10CTS", "15:05ICN",
             "직항", "왕복 702,600원~"]
    assert _standard_price_before_discount(clean, 0, clean.index("왕복 702,600원~")) is None

    # end-to-end: 파서가 일반가를 담는다.
    text = "\n".join(lines)
    url = "https://flight.naver.com/flights/international/ICN-CTS-20260703/CTS-ICN-20260707"
    cands = parse_naver_flight_text(text=text, source_url=url, limit=1)
    assert cands and cands[0].price == "왕복 722,600원~"
