from __future__ import annotations

from datetime import date

from travel_agent.app.agents.flight_live_search import flight_candidate_to_option
from travel_agent.app.connectors.flights.google_browser import parse_google_flight_text
from travel_agent.app.llm.flight_search_links import build_flight_search_links
from travel_agent.app.schemas.brief import TripBrief

SAMPLE = (
    "인기 항공편순으로 정렬됨 "
    "오전 8:20 – 오전 11:00 진에어대한항공 2시간 40분 ICN–CTS 직항 "
    "CO2e 144kg 평균 배출량 ₩734,300 왕복 "
    "오후 2:25 – 오후 4:00 에어서울 1시간 35분 ICN–FUK 직항 "
    "CO2e 80kg +19% 배출 ₩261,100 왕복"
)


def test_parse_google_flight_text() -> None:
    candidates = parse_google_flight_text(text=SAMPLE, source_url="https://g", limit=5)

    assert len(candidates) == 2
    first = candidates[0]
    assert first.provider == "google_flights"
    assert first.airline == "진에어대한항공"
    assert first.outbound_departure == "08:20"
    assert first.outbound_arrival == "11:00"
    assert first.inbound_departure is None
    assert "734,300" in first.price
    # 오후 2:25 -> 14:25 (24시간제 변환)
    assert candidates[1].outbound_departure == "14:25"


def test_google_candidate_to_flight_option() -> None:
    brief = TripBrief(
        origin="ICN",
        destinations=["Sapporo"],
        start_date=date(2026, 7, 7),
        end_date=date(2026, 7, 11),
        travelers=1,
        currency="KRW",
    )
    links = build_flight_search_links(brief)
    assert links is not None
    candidate = parse_google_flight_text(text=SAMPLE, source_url=links.google_url, limit=5)[0]

    option = flight_candidate_to_option(candidate, links, "KRW")

    assert option is not None
    assert option.price.amount == 734_300
    assert option.return_departure_time is None  # 구글은 오는 편 시각 미제공
    assert option.metadata.is_mock is False
    assert option.metadata.source_ref.provider == "google_flights"
    assert any("구글 항공" in note for note in option.notes)
