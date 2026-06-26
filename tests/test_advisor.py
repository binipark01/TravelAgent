from __future__ import annotations

from datetime import datetime

import pytest

from travel_agent.app.llm import advisor
from travel_agent.app.schemas.common import Location, Money, SourceRef
from travel_agent.app.schemas.providers import (
    AccommodationOption,
    FlightOption,
    ProviderMetadata,
)
from travel_agent.app.utils.ids import new_id
from travel_agent.app.utils.time import utc_now


def _meta() -> ProviderMetadata:
    now = utc_now()
    return ProviderMetadata(
        provider_name="test",
        retrieved_at=now,
        source_ref=SourceRef(
            source_id=new_id("src"), provider="test", title="t", reference="r", retrieved_at=now
        ),
    )


def _flight(option_id: str, airline: str, price: int) -> FlightOption:
    return FlightOption(
        option_id=option_id,
        airline=airline,
        origin="서울",
        destination="파리",
        departure_time=datetime(2026, 8, 3, 10, 0),
        arrival_time=datetime(2026, 8, 3, 18, 0),
        price=Money(amount=price, currency="KRW"),
        metadata=_meta(),
        notes=["경유: 1회 경유"],
    )


def _hotel(option_id: str, name: str, nightly: int) -> AccommodationOption:
    return AccommodationOption(
        option_id=option_id,
        name=name,
        location=Location(name="파리", area="르마레"),
        nightly_price=Money(amount=nightly, currency="KRW"),
        total_price=Money(amount=nightly * 4, currency="KRW"),
        rating=4.3,
        star_rating=4,
        metadata=_meta(),
        notes=[],
    )


def test_advise_disabled_returns_empty() -> None:
    # conftest의 autouse 픽스처가 ENABLE_LIVE_LLM=false → LLM 평 비활성.
    flights = [_flight("flt_1", "대한항공", 1200000)]
    advisor.advise_flights(flights, context="서울→파리")
    assert all(not n.startswith("💬") for n in flights[0].notes)


def test_advise_flights_prepends_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    comment = "경유지만 최저가, 시간 여유 있으면 추천"
    monkeypatch.setattr(
        advisor, "_advise", lambda items, *, kind_label, context: {"flt_1": comment}
    )
    flights = [_flight("flt_1", "중국국제항공", 1196200), _flight("flt_2", "대한항공", 1500000)]
    advisor.advise_flights(flights, context="서울→파리, 1명")
    assert flights[0].notes[0] == f"💬 {comment}"
    # 평이 없는 후보는 그대로.
    assert all(not n.startswith("💬") for n in flights[1].notes)


def test_advise_hotels_prepends_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        advisor,
        "_advise",
        lambda items, *, kind_label, context: {"htl_1": "르마레 역세권·평점 높음, 가성비 무난"},
    )
    hotels = [_hotel("htl_1", "Hotel A", 130000)]
    advisor.advise_hotels(hotels, context="파리, 2명, 4박")
    assert hotels[0].notes[0].startswith("💬 르마레")


def test_flight_desc_includes_price_and_stops() -> None:
    desc = advisor._flight_desc(_flight("flt_1", "대한항공", 1200000))
    assert "대한항공" in desc
    assert "1,200,000원" in desc
    assert "경유" in desc


# --- A1: 라이브 파싱 검증 (게이트 활성으로 보이게 + run_codex_json을 가짜 JSON으로) ---


def _enable_local(monkeypatch: pytest.MonkeyPatch) -> None:
    # advisor가 import한 게이트 헬퍼를 활성으로 보이게 한다(웹검색 불필요한 로컬 경로).
    monkeypatch.setattr(advisor, "live_llm_local_enabled", lambda settings: True)


def test_advise_parses_comments_object(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_local(monkeypatch)
    fake = {"comments": {"flt_1": "최저가지만 경유 길다", "flt_2": "  "}}
    monkeypatch.setattr(advisor, "run_codex_json", lambda *a, **k: fake)
    flights = [_flight("flt_1", "중국국제항공", 1196200), _flight("flt_2", "대한항공", 1500000)]
    advisor.advise_flights(flights, context="서울→파리")
    # 정상 평은 붙고, 공백뿐인 평은 버려진다.
    assert flights[0].notes[0] == "💬 최저가지만 경유 길다"
    assert all(not n.startswith("💬") for n in flights[1].notes)


def test_advise_accepts_bare_id_to_comment_map(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_local(monkeypatch)
    # 모델이 {comments:{...}} 대신 {id: 평}을 바로 줄 수도 있다 — 그 형식도 받아들인다.
    monkeypatch.setattr(advisor, "run_codex_json", lambda *a, **k: {"htl_1": "역세권·가성비"})
    hotels = [_hotel("htl_1", "Hotel A", 130000)]
    advisor.advise_hotels(hotels, context="파리")
    assert hotels[0].notes[0].startswith("💬 역세권")


def test_advise_malformed_json_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_local(monkeypatch)
    # run_codex_json이 None(파싱 실패)이거나 dict가 아니어도 조용히 no-op.
    for bad in (None, "not-a-dict", {"comments": "wrong-type"}):
        monkeypatch.setattr(advisor, "run_codex_json", lambda *a, _b=bad, **k: _b)
        flights = [_flight("flt_1", "대한항공", 1200000)]
        advisor.advise_flights(flights, context="서울→파리")
        assert all(not n.startswith("💬") for n in flights[0].notes)


def test_estimate_daily_costs_parses_and_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_local(monkeypatch)
    monkeypatch.setattr(
        advisor, "run_codex_json", lambda *a, **k: {"food": 90000, "local_transport": 12000}
    )
    assert advisor.estimate_daily_costs("파리", travel_style=None, currency="KRW") == (90000, 12000)


def test_estimate_daily_costs_rejects_bad_values(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_local(monkeypatch)
    # 키 누락·음수·0·타입오류·non-dict는 모두 None(기본값 폴백 유도).
    bad_payloads = [
        {"food": 90000},  # local_transport 누락
        {"food": 0, "local_transport": 12000},  # 0 이하
        {"food": -1, "local_transport": 12000},  # 음수
        {"food": "x", "local_transport": 12000},  # 타입 오류
        None,  # 파싱 실패
    ]
    for bad in bad_payloads:
        monkeypatch.setattr(advisor, "run_codex_json", lambda *a, _b=bad, **k: _b)
        assert advisor.estimate_daily_costs("파리", travel_style="럭셔리", currency="KRW") is None
