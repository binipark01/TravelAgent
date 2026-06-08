from __future__ import annotations

from datetime import date, timedelta

from travel_agent.app.agents.flight_live_search import (
    _candidate_departures,
    _curate,
    _search_window,
    flight_candidate_to_option,
)
from travel_agent.app.llm.flight_search_links import _codes_for, build_flight_search_links
from travel_agent.app.schemas.brief import TripBrief
from travel_agent.app.schemas.llm import FlightFareCandidate


def _links():
    brief = TripBrief(
        origin="서울",
        destinations=["Sapporo"],
        start_date=date(2026, 7, 3),
        end_date=date(2026, 7, 15),
        travelers=1,
        currency="KRW",
    )
    links = build_flight_search_links(brief)
    assert links is not None
    return links


def test_flight_candidate_to_option_parses_real_fields() -> None:
    links = _links()
    candidate = FlightFareCandidate(
        provider="naver_flight",
        airline="이스타항공",
        outbound_departure="09:20 ICN",
        outbound_arrival="11:50 CTS",
        inbound_departure="12:55 CTS",
        inbound_arrival="16:00 ICN",
        outbound_duration="직항, 02시간 30분",
        inbound_duration="직항, 03시간 05분",
        price="왕복 550,600원~",
        stops="직항",
        source_url=links.naver_url,
        notes=[],
    )

    option = flight_candidate_to_option(candidate, links, "KRW")

    assert option is not None
    assert option.airline == "이스타항공"
    assert option.origin == "서울"
    assert option.destination == "Sapporo"
    assert option.departure_time.hour == 9
    assert option.departure_time.minute == 20
    assert option.arrival_time.hour == 11
    assert option.arrival_time.minute == 50
    assert option.return_departure_time is not None
    assert option.return_departure_time.hour == 12
    assert option.return_departure_time.minute == 55
    # "왕복 550,600원~" -> 550600 (실제 운임 숫자만 추출)
    assert option.price.amount == 550_600
    assert option.price.currency == "KRW"
    # 실데이터이므로 mock이 아님
    assert option.metadata.is_mock is False
    assert option.metadata.source_ref.is_live is True
    assert option.metadata.source_ref.provider == "naver_flight"


def test_flight_candidate_one_way_has_no_return() -> None:
    brief = TripBrief(
        origin="서울",
        destinations=["Tokyo"],
        start_date=date(2026, 9, 1),
        travelers=1,
        currency="KRW",
    )
    links = build_flight_search_links(brief)
    assert links is not None
    candidate = FlightFareCandidate(
        provider="naver_flight",
        airline="대한항공",
        outbound_departure="08:20 ICN",
        outbound_arrival="10:40 NRT",
        inbound_departure=None,
        inbound_arrival=None,
        outbound_duration="직항, 02시간 20분",
        inbound_duration=None,
        price="편도 210,000원~",
        stops="직항",
        source_url=links.naver_url,
        notes=[],
    )

    option = flight_candidate_to_option(candidate, links, "KRW")

    assert option is not None
    assert option.return_departure_time is None
    assert option.return_arrival_time is None
    assert option.price.amount == 210_000


def test_place_normalization_maps_aliases() -> None:
    # LLM이 영어·국가병기·한글로 줘도 공항코드로 정규화된다.
    assert _codes_for("Seoul, South Korea") == ("ICN", "sel")
    assert _codes_for("서울") == ("ICN", "sel")
    assert _codes_for("Fukuoka, Japan") == ("FUK", "fuk")
    # 메트로코드 대신 대표 공항코드를 쓴다(네이버가 TYO/OSA는 결과 없음).
    assert _codes_for("Tokyo")[0] == "NRT"
    assert _codes_for("오사카")[0] == "KIX"
    # LLM이 IATA 코드를 직접 줘도(예: origin="ICN") 인식한다.
    assert _codes_for("ICN") == ("ICN", "sel")
    assert _codes_for("CTS") == ("CTS", "cts")
    assert _codes_for("TYO")[0] == "NRT"
    # 국가명만 줘도 출발지는 한국(인천)으로 본다.
    assert _codes_for("대한민국") == ("ICN", "sel")
    assert _codes_for("South Korea") == ("ICN", "sel")
    assert _codes_for("Unknownville") is None


def test_build_links_with_english_origin_and_metro_city() -> None:
    brief = TripBrief(
        origin="Seoul, South Korea",
        destinations=["Tokyo"],
        start_date=date(2026, 10, 15),
        end_date=date(2026, 10, 18),
        travelers=1,
        currency="KRW",
    )
    links = build_flight_search_links(brief)

    assert links is not None
    assert "ICN-NRT-20261015" in links.naver_url


def test_search_window_expands_for_flexible_dates() -> None:
    brief = TripBrief(
        origin="ICN",
        destinations=["Bangkok"],
        start_date=date(2026, 7, 7),
        end_date=date(2026, 7, 12),
        duration_nights=5,
        flexible_dates=True,
        currency="KRW",
    )

    start, end = _search_window(brief, 5)
    deps = _candidate_departures(start, end, 5, 9)

    # 유연 일정: 출발일 ±3일(7/4~7/10)을 검색한다.
    assert start == date(2026, 7, 4)
    assert deps[0] == date(2026, 7, 4)
    assert deps[-1] == date(2026, 7, 10)
    assert len(deps) == 7


def test_search_window_keeps_exact_dates() -> None:
    brief = TripBrief(
        origin="ICN",
        destinations=["Okinawa"],
        start_date=date(2026, 9, 20),
        end_date=date(2026, 9, 23),
        duration_nights=3,
        flexible_dates=False,
        currency="KRW",
    )

    start, end = _search_window(brief, 3)
    deps = _candidate_departures(start, end, 3, 9)

    # 정확한 날짜를 준 경우 단일 날짜만 검색한다.
    assert (start, end) == (date(2026, 9, 20), date(2026, 9, 23))
    assert deps == [date(2026, 9, 20)]


def test_candidate_departures_spreads_across_flexible_window() -> None:
    deps = _candidate_departures(date(2026, 7, 3), date(2026, 7, 15), 4, 3)

    assert deps == [date(2026, 7, 3), date(2026, 7, 7), date(2026, 7, 11)]
    # 모든 출발일은 4박을 더해도 window 끝(7/15) 안에 들어간다.
    assert all(departure + timedelta(days=4) <= date(2026, 7, 15) for departure in deps)


def test_candidate_departures_single_for_fixed_window() -> None:
    # 범위 == 여행 길이(4박) → 출발일 후보는 하나뿐.
    deps = _candidate_departures(date(2026, 10, 3), date(2026, 10, 7), 4, 3)

    assert deps == [date(2026, 10, 3)]


def test_noise_airline_is_dropped() -> None:
    links = _links()
    candidate = FlightFareCandidate(
        provider="naver_flight",
        airline="항공권 가격 변동 그래프",
        outbound_departure="07:25 ICN",
        outbound_arrival="11:50 CTS",
        inbound_departure="12:55 CTS",
        inbound_arrival="16:00 ICN",
        outbound_duration="직항, 02시간 30분",
        inbound_duration="직항, 03시간 05분",
        price="왕복 539,800원",
        stops="직항",
        source_url=links.naver_url,
        notes=[],
    )

    # UI 텍스트가 항공사명으로 잘못 들어오면 후보에서 제외한다.
    assert flight_candidate_to_option(candidate, links, "KRW") is None


def test_candidate_departures_covers_full_window() -> None:
    # 7/3~7/15, 4박 → 출발 가능일 7/3~7/11(9일)을 빠짐없이 검색한다.
    deps = _candidate_departures(date(2026, 7, 3), date(2026, 7, 15), 4, 9)

    assert deps == [date(2026, 7, 3) + timedelta(days=offset) for offset in range(9)]
    assert deps[0] == date(2026, 7, 3)
    assert deps[-1] == date(2026, 7, 11)


def _option(outbound: str, inbound: str, price: str) -> object:
    links = _links()
    candidate = FlightFareCandidate(
        provider="naver_flight",
        airline="테스트항공",
        outbound_departure=outbound,
        outbound_arrival="11:50 CTS",
        inbound_departure=inbound,
        inbound_arrival="20:00 ICN",
        outbound_duration="직항, 02시간 30분",
        inbound_duration="직항, 03시간 05분",
        price=price,
        stops="직항",
        source_url=links.naver_url,
        notes=[],
    )
    option = flight_candidate_to_option(candidate, links, "KRW")
    assert option is not None
    return option


def test_curate_prefers_schedule_match_over_cheaper_mismatch() -> None:
    brief = TripBrief(
        origin="서울",
        destinations=["Sapporo"],
        start_date=date(2026, 7, 3),
        end_date=date(2026, 7, 15),
        travelers=1,
        currency="KRW",
        transport_preference="flight, outbound_morning, return_afternoon",
    )
    match_pricey = _option("09:20 ICN", "15:00 CTS", "왕복 600,000원")  # 오전출발+오후귀국
    mismatch_cheap = _option("19:00 ICN", "08:00 CTS", "왕복 500,000원")  # 저녁출발+오전귀국
    match_pricier = _option("07:00 ICN", "13:00 CTS", "왕복 650,000원")  # 오전출발+오후귀국

    curated = _curate([mismatch_cheap, match_pricey, match_pricier], brief, limit=3)

    # 조건 충족 후보가 더 싸지 않아도 위로 온다.
    assert curated[0] is match_pricey
    assert curated[1] is match_pricier
    assert curated[2] is mismatch_cheap
    # 조건 충족 후보엔 이유 태그가 붙는다.
    assert any("요청한 시간대 조건 충족" in note for note in match_pricey.notes)
    assert any("오전 출발" in note for note in match_pricey.notes)
    # 추천 중 최저가 후보(여기선 mismatch_cheap)엔 최저가 태그가 붙는다.
    assert any("추천 중 최저가" in note for note in mismatch_cheap.notes)


def _option_on(start: date, outbound: str, inbound: str, price: str) -> object:
    brief = TripBrief(
        origin="서울",
        destinations=["Sapporo"],
        start_date=start,
        end_date=start + timedelta(days=4),
        travelers=1,
        currency="KRW",
    )
    links = build_flight_search_links(brief)
    assert links is not None
    candidate = FlightFareCandidate(
        provider="naver_flight",
        airline="테스트항공",
        outbound_departure=outbound,
        outbound_arrival="13:00 CTS",
        inbound_departure=inbound,
        inbound_arrival="18:00 ICN",
        outbound_duration="직항, 02시간 30분",
        inbound_duration="직항, 02시간 30분",
        price=price,
        stops="직항",
        source_url=links.naver_url,
        notes=[],
    )
    option = flight_candidate_to_option(candidate, links, "KRW")
    assert option is not None
    return option


def test_curate_diversifies_across_departure_dates() -> None:
    brief = TripBrief(
        origin="서울",
        destinations=["Sapporo"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 15),
        travelers=1,
        currency="KRW",
    )
    options = [
        _option_on(date(2026, 7, 5), "09:00 ICN", "14:00 CTS", "왕복 550,000원"),
        _option_on(date(2026, 7, 5), "10:00 ICN", "14:00 CTS", "왕복 560,000원"),  # 같은 날 2번째
        _option_on(date(2026, 7, 9), "09:00 ICN", "14:00 CTS", "왕복 600,000원"),
        _option_on(date(2026, 7, 11), "09:00 ICN", "14:00 CTS", "왕복 620,000원"),
    ]

    curated = _curate(options, brief, limit=3)

    # 한 날짜에 쏠리지 않고 서로 다른 3개 날짜가 나온다.
    dates = {option.departure_time.date() for option in curated}
    assert dates == {date(2026, 7, 5), date(2026, 7, 9), date(2026, 7, 11)}


def _google_option(start: date, outbound: str, price: str) -> object:
    brief = TripBrief(
        origin="ICN",
        destinations=["Sapporo"],
        start_date=start,
        end_date=start + timedelta(days=4),
        travelers=1,
        currency="KRW",
    )
    links = build_flight_search_links(brief)
    assert links is not None
    candidate = FlightFareCandidate(
        provider="google_flights",
        airline="구글표시항공",
        outbound_departure=outbound,
        outbound_arrival="13:00 CTS",
        inbound_departure=None,
        inbound_arrival=None,
        outbound_duration="2시간 30분",
        inbound_duration=None,
        price=price,
        stops="직항",
        source_url=links.google_url,
        notes=[],
    )
    option = flight_candidate_to_option(candidate, links, "KRW")
    assert option is not None
    return option


def test_curate_includes_both_sources() -> None:
    brief = TripBrief(
        origin="ICN",
        destinations=["Sapporo"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 15),
        travelers=1,
        currency="KRW",
    )
    naver = [
        _option_on(date(2026, 7, 5), "09:00 ICN", "14:00 CTS", "왕복 550,000원"),
        _option_on(date(2026, 7, 9), "09:00 ICN", "14:00 CTS", "왕복 560,000원"),
        _option_on(date(2026, 7, 11), "09:00 ICN", "14:00 CTS", "왕복 570,000원"),
    ]
    google = [
        _google_option(date(2026, 7, 6), "08:00 ICN", "₩600,000 왕복"),
        _google_option(date(2026, 7, 10), "08:00 ICN", "₩610,000 왕복"),
    ]

    curated = _curate(naver + google, brief, limit=4)

    providers = {option.metadata.source_ref.provider for option in curated}
    # 네이버가 시간대 조건상 더 유리해도 구글이 묻히지 않고 둘 다 노출된다.
    assert "naver_flight" in providers
    assert "google_flights" in providers


def test_curate_detects_korean_schedule_preference() -> None:
    # LLM이 한글 자연어로 선호를 줘도 오전출발을 인식해야 한다.
    brief = TripBrief(
        origin="서울",
        destinations=["Sapporo"],
        start_date=date(2026, 7, 3),
        end_date=date(2026, 7, 15),
        travelers=1,
        currency="KRW",
        transport_preference="삿포로행 오전 출발, 인천행 오후 출발 항공편",
    )
    afternoon_cheap = _option("13:50 ICN", "12:55 CTS", "왕복 500,000원")  # 오후출발(더 쌈)
    morning_pricey = _option("09:20 ICN", "12:55 CTS", "왕복 540,000원")  # 오전출발+오후귀국

    curated = _curate([afternoon_cheap, morning_pricey], brief, limit=2)

    # 가격이 더 비싸도 '오전 출발' 조건을 만족하는 후보가 위로 온다.
    assert curated[0] is morning_pricey
    assert any("오전 출발" in note for note in morning_pricey.notes)
