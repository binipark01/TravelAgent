from __future__ import annotations

from travel_agent.app.agents.budget import BudgetAgent
from travel_agent.app.schemas.brief import TripBrief
from travel_agent.app.schemas.common import FindingSeverity, Location, Money, SourceRef
from travel_agent.app.schemas.providers import AccommodationOption, FlightOption, ProviderMetadata
from travel_agent.app.schemas.trip import TripPlanState
from travel_agent.app.utils.ids import new_id
from travel_agent.app.utils.time import expires_in, utc_now


def _meta() -> ProviderMetadata:
    now = utc_now()
    ref = SourceRef(
        source_id=new_id("s"),
        provider="naver_flight",
        source_url="https://x",
        title="t",
        reference="r",
        retrieved_at=now,
        expires_at=expires_in(1),
        is_live=True,
        is_mock=False,
        source_type="public_page",
        confidence=0.7,
        freshness_note="n",
    )
    return ProviderMetadata(
        provider_name="naver_flight",
        retrieved_at=now,
        source_ref=ref,
        expires_at=expires_in(1),
        is_mock=False,
    )


def _flight(amount: int) -> FlightOption:
    now = utc_now()
    return FlightOption(
        option_id=new_id("f"),
        airline="A",
        origin="ICN",
        destination="CTS",
        departure_time=now,
        arrival_time=now,
        price=Money(amount=amount, currency="KRW"),
        metadata=_meta(),
        notes=[],
    )


def _hotel(total: int) -> AccommodationOption:
    return AccommodationOption(
        option_id=new_id("h"),
        name="H",
        location=Location(name="Sapporo", country=None, area=None),
        nightly_price=Money(amount=total // 3, currency="KRW"),
        total_price=Money(amount=total, currency="KRW"),
        metadata=_meta(),
        notes=[],
    )


def test_budget_uses_min_prices_and_real_warning() -> None:
    state = TripPlanState(trip_id="t", raw_user_message="m", currency="KRW")
    state.brief = TripBrief(travelers=1, duration_days=3, currency="KRW")
    # 정렬 순서와 무관하게 최저가를 잡아야 한다(비싼 것 먼저 넣음).
    state.transport_options = [_flight(600_000), _flight(450_000)]
    state.accommodation_options = [_hotel(300_000), _hotel(240_000)]

    BudgetAgent().run(state)

    assert state.budget is not None
    assert state.budget.breakdown.flights == 450_000
    assert state.budget.breakdown.accommodation == 240_000
    # 실데이터 기반 경고 + 항상 남는 투명성(info) finding
    assert any("실시간" in warning for warning in state.budget.budget_warnings)
    assert any(finding.severity == FindingSeverity.info for finding in state.critic_findings)
    assert all("mock" not in warning for warning in state.budget.budget_warnings)
