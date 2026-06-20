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
    per_day_estimated_cost: float | None = None  # 1인 1일 현지 경비(식비+교통+입장료)
    total_local_label: str | None = None  # 현지 통화 환산 총액(예: "약 ¥123,000")
    breakdown: BudgetBreakdown
    currency: str = "KRW"
    confidence: str = "medium"
    budget_warnings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
