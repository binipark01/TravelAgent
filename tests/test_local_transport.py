from __future__ import annotations

from datetime import time

from travel_agent.app.agents.route_optimizer import RouteAgent
from travel_agent.app.connectors.routes.local_transport import (
    lookup_local_transport,
    resolve_city,
)
from travel_agent.app.providers.base import build_mock_provider_bundle
from travel_agent.app.schemas.brief import TripBrief
from travel_agent.app.schemas.itinerary import DayPlan, Itinerary, TransferSegment
from travel_agent.app.schemas.providers import LocalTransportItem
from travel_agent.app.schemas.trip import TripPlanState
from travel_agent.app.utils.ids import new_id


def test_resolve_city_handles_aliases() -> None:
    assert resolve_city("Sapporo") == "삿포로"
    assert resolve_city("삿포로") == "삿포로"
    assert resolve_city("Tokyo, Japan") == "도쿄"
    assert resolve_city("다낭") == "다낭"
    assert resolve_city("Nowhere City") is None


def test_lookup_returns_transfers_and_passes() -> None:
    plan = lookup_local_transport("삿포로")
    assert plan is not None
    assert plan.city == "삿포로"
    assert len(plan.airport_transfers) >= 1
    assert len(plan.transit_passes) >= 1
    assert all(item.category == "airport" for item in plan.airport_transfers)
    assert all(item.category == "pass" for item in plan.transit_passes)
    assert plan.source_url
    assert plan.metadata.is_mock is False


def test_lookup_unknown_city_is_none() -> None:
    assert lookup_local_transport("Reykjavik") is None


def test_okinawa_recommends_rental_car() -> None:
    plan = lookup_local_transport("오키나와")
    assert plan is not None
    names = [item.name for item in plan.airport_transfers]
    assert any("렌터카" in name for name in names)


# --- 운행정보(frequency/hours) 추가 ---


def test_local_transport_item_serializes_schedule_fields() -> None:
    # additive 필드가 직렬화에 포함된다(미지정 시 None).
    item = LocalTransportItem(
        category="airport", name="X선", frequency="약 15분 간격", hours="첫차 06:00"
    )
    dumped = item.model_dump(mode="json")
    assert dumped["frequency"] == "약 15분 간격"
    assert dumped["hours"] == "첫차 06:00"
    bare = LocalTransportItem(category="airport", name="Y선")
    assert bare.model_dump(mode="json")["frequency"] is None
    assert bare.model_dump(mode="json")["hours"] is None


def test_static_data_has_frequency_on_major_routes() -> None:
    # 웹검색으로 확인한 주요 노선엔 운행간격이 채워져 있다(전부는 아님 — 미확인은 None).
    osaka = lookup_local_transport("오사카")
    assert osaka is not None
    rapit = next(t for t in osaka.airport_transfers if "라피트" in t.name)
    assert rapit.frequency  # 라피트는 운행간격 확인됨
    haruka = next(t for t in osaka.airport_transfers if "하루카" in t.name)
    assert haruka.frequency and haruka.hours
    # 확신 없는 항목(난카이 공항급행)은 None으로 비워 둔다(빈칸이 오답보다 낫다).
    express = next(t for t in osaka.airport_transfers if "공항급행" in t.name)
    assert express.frequency is None

    tokyo = lookup_local_transport("도쿄")
    assert tokyo is not None
    assert any(t.frequency for t in tokyo.airport_transfers)


def _state(destination: str) -> TripPlanState:
    return TripPlanState(
        trip_id="t",
        raw_user_message="m",
        selected_destination=destination,
        brief=TripBrief(currency="KRW", destinations=[destination]),
    )


def _xfer(origin: str, dest: str, minutes: int, mode: str) -> TransferSegment:
    return TransferSegment(
        item_id=new_id("x"),
        origin=origin,
        destination=dest,
        start_time=time(10, 0),
        end_time=time(10, 0),
        travel_minutes=minutes,
        mode=mode,
    )


def test_route_agent_enriches_airport_transfer_with_frequency() -> None:
    state = _state("오사카")
    airport = _xfer("간사이공항(도착)", "난바 일대", 45, "난카이 라피트(특급)")
    inner = _xfer("호텔", "기요미즈데라", 20, "지하철")
    itin = Itinerary(days=[DayPlan(day=1, transfers=[airport, inner])], summary="s")

    RouteAgent(build_mock_provider_bundle().routes)._apply_airport_transfer_info(itin, state)
    # 공항 이동엔 매칭 교통의 운행간격이 붙는다(특정 출발시각은 만들지 않는다).
    assert "간격" in itin.days[0].transfers[0].mode
    assert "약 30분 간격" in itin.days[0].transfers[0].mode
    # 공항 아닌 이동은 그대로.
    assert itin.days[0].transfers[1].mode == "지하철"


def test_route_agent_airport_enrichment_is_idempotent() -> None:
    state = _state("오사카")
    airport = _xfer("간사이공항(도착)", "난바 일대", 45, "난카이 라피트(특급)")
    itin = Itinerary(days=[DayPlan(day=1, transfers=[airport])], summary="s")
    agent = RouteAgent(build_mock_provider_bundle().routes)
    agent._apply_airport_transfer_info(itin, state)
    once = itin.days[0].transfers[0].mode
    agent._apply_airport_transfer_info(itin, state)
    assert itin.days[0].transfers[0].mode == once  # 운행간격이 중복으로 붙지 않는다


def test_route_agent_no_match_keeps_mode() -> None:
    # 운행정보가 없는 도시(데이터셋 밖)면 mode를 건드리지 않는다(폴백).
    state = _state("Reykjavik")
    airport = _xfer("케플라비크공항", "시내", 50, "공항버스")
    itin = Itinerary(days=[DayPlan(day=1, transfers=[airport])], summary="s")
    RouteAgent(build_mock_provider_bundle().routes)._apply_airport_transfer_info(itin, state)
    assert itin.days[0].transfers[0].mode == "공항버스"
