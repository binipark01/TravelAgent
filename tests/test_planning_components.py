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
