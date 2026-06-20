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
