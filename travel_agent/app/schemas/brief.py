from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from travel_agent.app.schemas.common import StrictBaseModel


class TripBrief(StrictBaseModel):
    origin: str | None = None
    destination_hint: str | None = None
    destinations: list[str] = Field(default_factory=list)
    selected_destination: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    flexible_dates: bool = False
    duration_days: int | None = None
    duration_nights: int | None = None
    traveler_count: int | None = None
    adults: int | None = None
    children: int | None = None
    travelers: int | None = None
    budget_total: float | None = None
    budget_per_person: float | None = None
    currency: str = "KRW"
    travel_style: str | None = None
    pace: str | None = None
    accommodation_preference: str | None = None
    transport_preference: str | None = None
    accessibility_needs: list[str] = Field(default_factory=list)
    dietary_restrictions: list[str] = Field(default_factory=list)
    passport_country: str | None = None
    visa_status_known: bool = False
    must_include: list[str] = Field(default_factory=list)
    must_avoid: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _drop_nulls(cls, data: object) -> object:
        # LLM이 필드를 null로 주는 경우가 있어, null은 제거하고 기본값을 쓰게 한다.
        if isinstance(data, dict):
            return {key: value for key, value in data.items() if value is not None}
        return data


class IntakeResult(StrictBaseModel):
    brief: TripBrief
    questions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
