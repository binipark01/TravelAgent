from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class TripStatus(StrEnum):
    intake = "intake"
    needs_user_input = "needs_user_input"
    researching = "researching"
    drafting = "drafting"
    validating = "validating"
    needs_approval = "needs_approval"
    ready = "ready"
    booking_in_progress = "booking_in_progress"
    completed = "completed"
    failed = "failed"


class FindingSeverity(StrEnum):
    info = "info"
    warning = "warning"
    blocking = "blocking"


class FindingCategory(StrEnum):
    budget = "budget"
    route = "route"
    visa = "visa"
    availability = "availability"
    safety = "safety"
    missing_input = "missing_input"
    source_quality = "source_quality"
    policy = "policy"


class SourceRef(StrictBaseModel):
    source_id: str
    provider: str
    provider_ref: str | None = None
    source_url: str | None = None
    title: str
    reference: str
    retrieved_at: datetime
    expires_at: datetime | None = None
    is_live: bool = False
    is_mock: bool = True
    source_type: str = "mock"
    confidence: float = 0.5
    attribution: str | None = None
    license_notes: str | None = None
    freshness_note: str = "Mock provider response; verify with official source before booking."


class Money(StrictBaseModel):
    amount: float
    currency: str = "KRW"


class Location(StrictBaseModel):
    name: str
    country: str | None = None
    area: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class CriticFinding(StrictBaseModel):
    severity: FindingSeverity
    category: FindingCategory
    message: str
    suggested_fix: str | None = None
    affected_plan_items: list[str] = Field(default_factory=list)


class AuditEvent(StrictBaseModel):
    event_id: str
    event_type: str
    message: str
    created_at: datetime
    actor: str = "system"
