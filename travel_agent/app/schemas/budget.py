from __future__ import annotations

from pydantic import Field

from travel_agent.app.schemas.common import StrictBaseModel


class BudgetBreakdown(StrictBaseModel):
    flights: float = 0
    accommodation: float = 0
    food: float = 0
    local_transport: float = 0
    activities: float = 0
    buffer: float = 0


class BudgetEstimate(StrictBaseModel):
    total_estimated_cost: float
    per_person_estimated_cost: float
    breakdown: BudgetBreakdown
    currency: str = "KRW"
    confidence: str = "medium"
    budget_warnings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
