from __future__ import annotations

from datetime import date

from travel_agent.app.agents.budget import BudgetAgent
from travel_agent.app.agents.critic import PlanCriticAgent
from travel_agent.app.agents.poi import RestaurantAgent
from travel_agent.app.agents.route_optimizer import RouteAgent
from travel_agent.app.providers.base import build_mock_provider_bundle
from travel_agent.app.schemas.brief import TripBrief
from travel_agent.app.schemas.common import FindingSeverity
from travel_agent.app.schemas.trip import TripPlanState


def test_route_optimization_basic_feasibility() -> None:
    providers = build_mock_provider_bundle()
    state = TripPlanState(
        trip_id="trip_route",
        raw_user_message="test",
        currency="KRW",
        selected_destination="Osaka",
        brief=TripBrief(
            origin="서울",
            destinations=["Japan"],
            start_date=date(2026, 10, 3),
            end_date=date(2026, 10, 7),
            duration_days=5,
            travelers=2,
            currency="KRW",
        ),
    )
    RestaurantAgent(providers.places).run(state)
    RouteAgent(providers.routes).run(state)

    assert state.optimized_itinerary is not None
    assert len(state.optimized_itinerary.days) == 5
    assert all(len(day.items) <= 4 for day in state.optimized_itinerary.days)


def test_budget_overrun_detection() -> None:
    providers = build_mock_provider_bundle()
    state = TripPlanState(
        trip_id="trip_budget",
        raw_user_message="test",
        currency="KRW",
        selected_destination="Osaka",
        brief=TripBrief(
            origin="서울",
            destinations=["Japan"],
            start_date=date(2026, 10, 3),
            end_date=date(2026, 10, 7),
            duration_days=5,
            travelers=2,
            budget_total=500_000,
            currency="KRW",
        ),
    )
    RestaurantAgent(providers.places).run(state)
    RouteAgent(providers.routes).run(state)
    BudgetAgent().run(state)

    assert state.budget is not None
    assert any(f.severity == FindingSeverity.blocking for f in state.critic_findings)


def test_budget_computes_per_day_cost() -> None:
    from datetime import date as date_cls
    from datetime import datetime

    from travel_agent.app.schemas.common import Money, SourceRef
    from travel_agent.app.schemas.providers import FlightOption, ProviderMetadata

    now = datetime(2026, 1, 1)
    ref = SourceRef(source_id="s", provider="t", title="t", reference="r", retrieved_at=now)
    meta = ProviderMetadata(provider_name="t", retrieved_at=now, source_ref=ref)
    state = TripPlanState(
        trip_id="trip_pd",
        raw_user_message="test",
        currency="KRW",
        selected_destination="Osaka",
        brief=TripBrief(
            origin="서울",
            destinations=["Osaka"],
            start_date=date_cls(2026, 10, 3),
            end_date=date_cls(2026, 10, 6),
            duration_days=4,
            travelers=2,
            currency="KRW",
        ),
    )
    state.transport_options = [
        FlightOption(
            option_id="f1",
            airline="대한항공",
            origin="서울",
            destination="Osaka",
            departure_time=datetime(2026, 10, 3, 9),
            arrival_time=datetime(2026, 10, 3, 11),
            price=Money(amount=300_000, currency="KRW"),
            metadata=meta,
        )
    ]
    BudgetAgent().run(state)
    assert state.budget is not None
    # 항공은 표시 운임 그대로(과대계상 방지).
    assert state.budget.breakdown.flights == 300_000
    # 1인 1일 현지경비가 채워진다(LLM 꺼지면 기본값 기반).
    assert state.budget.per_day_estimated_cost is not None
    assert state.budget.per_day_estimated_cost > 0


def test_critic_blocking_findings() -> None:
    from datetime import date

    # 누락 정보로는 더 이상 차단하지 않는다. 실제 모순(종료일 < 시작일)만 blocking이다.
    state = TripPlanState(trip_id="trip_critic", raw_user_message="일본 여행")
    state.brief = TripBrief(
        currency="KRW",
        destinations=["Japan"],
        start_date=date(2026, 10, 7),
        end_date=date(2026, 10, 3),
    )
    PlanCriticAgent().run(state)

    assert any(f.severity == FindingSeverity.blocking for f in state.critic_findings)
