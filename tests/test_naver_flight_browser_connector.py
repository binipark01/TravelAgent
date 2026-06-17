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
    assert options[0].price == "왕복 569,900원~"
    assert options[0].stops == "직항"
    assert options[1].airline == "대한항공"
    assert options[1].price == "왕복 689,100원~"
