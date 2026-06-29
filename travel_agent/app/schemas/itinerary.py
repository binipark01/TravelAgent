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
    # POI 평점(트리플 실데이터 등). 프론트가 별점으로 표시. 없으면 미표시.
    rating: float | None = None


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
    # 지도에 좌표로 바로 찍기 위한 실좌표(트리플 스토어 등). 없으면 프론트가 이름 지오코딩.
    latitude: float | None = None
    longitude: float | None = None


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
    weather: str | None = None
    items: list[ItineraryItem] = Field(default_factory=list)
    meals: list[MealSuggestion] = Field(default_factory=list)
    transfers: list[TransferSegment] = Field(default_factory=list)
    free_time: list[FreeTimeBlock] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class Itinerary(StrictBaseModel):
    days: list[DayPlan] = Field(default_factory=list)
    summary: str = ""
    feasibility_flags: list[str] = Field(default_factory=list)
