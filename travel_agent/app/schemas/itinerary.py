from __future__ import annotations

from datetime import date as date_cls
from datetime import time

from pydantic import Field

from travel_agent.app.schemas.common import Location, Money, StrictBaseModel


class ItineraryItem(StrictBaseModel):
    item_id: str
    title: str
    type: str
    location: Location
    start_time: time
    end_time: time
    estimated_cost: Money
    booking_required: bool = False
    source_refs: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    feasibility_flags: list[str] = Field(default_factory=list)


class MealSuggestion(StrictBaseModel):
    item_id: str
    meal_type: str
    title: str
    area: str
    start_time: time
    end_time: time
    estimated_cost: Money
    source_refs: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class TransferSegment(StrictBaseModel):
    item_id: str
    origin: str
    destination: str
    start_time: time
    end_time: time
    travel_minutes: int
    mode: str = "transit"
    source_refs: list[str] = Field(default_factory=list)
    feasibility_flags: list[str] = Field(default_factory=list)


class FreeTimeBlock(StrictBaseModel):
    item_id: str
    title: str
    start_time: time
    end_time: time
    notes: list[str] = Field(default_factory=list)


class DayPlan(StrictBaseModel):
    day: int
    date: date_cls | None = None
    area: str | None = None
    items: list[ItineraryItem] = Field(default_factory=list)
    meals: list[MealSuggestion] = Field(default_factory=list)
    transfers: list[TransferSegment] = Field(default_factory=list)
    free_time: list[FreeTimeBlock] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class Itinerary(StrictBaseModel):
    days: list[DayPlan] = Field(default_factory=list)
    summary: str = ""
    feasibility_flags: list[str] = Field(default_factory=list)
