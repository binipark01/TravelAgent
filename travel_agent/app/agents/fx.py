from __future__ import annotations

from travel_agent.app.connectors.fx.exchange_rate import fetch_fx_info
from travel_agent.app.schemas.trip import TripPlanState


class FxAgent:
    """목적지 통화로의 실시간 환율과 예산 환산을 채운다(예산 계산 후 실행)."""

    def run(self, state: TripPlanState) -> TripPlanState:
        brief = state.brief
        destination = state.selected_destination or (
            brief.destinations[0] if brief and brief.destinations else None
        )
        if not destination:
            return state
        budget_total = state.budget.total_estimated_cost if state.budget else None
        info = fetch_fx_info(
            destination, base_currency=state.currency, budget_total_base=budget_total
        )
        if info is not None:
            state.fx_info = info
        return state
