from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from travel_agent.app.schemas.common import StrictBaseModel
from travel_agent.app.utils.ids import new_id
from travel_agent.app.utils.time import utc_now


class EvidenceCategory(StrEnum):
    flight = "flight"
    accommodation = "accommodation"
    destination = "destination"
    poi = "poi"
    route = "route"
    weather = "weather"
    fx = "fx"
    visa = "visa"
    safety = "safety"
    activity = "activity"


class EvidenceSourceRef(StrictBaseModel):
    source_id: str = Field(default_factory=lambda: new_id("source"))
    provider: str
    provider_ref: str | None = None
    source_url: str | None = None
    retrieved_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None
    is_live: bool = False
    is_mock: bool = True
    source_type: str = "mock"
    confidence: float = 0.5
    attribution: str | None = None
    license_notes: str | None = None


class EvidencePacket(StrictBaseModel):
    evidence_id: str = Field(default_factory=lambda: new_id("evidence"))
    trip_id: str
    run_id: str
    category: EvidenceCategory
    normalized_data: dict[str, Any]
    source_refs: list[EvidenceSourceRef] = Field(default_factory=list)
    collected_by_agent: str
    collected_by_tool: str
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None
    freshness_policy: str = "verify_before_booking"
    confidence: float = 0.5
