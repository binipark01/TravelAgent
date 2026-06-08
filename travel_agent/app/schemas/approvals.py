from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from travel_agent.app.schemas.common import Money, StrictBaseModel


class ApprovalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"


class ApprovalRequest(StrictBaseModel):
    approval_id: str
    trip_id: str
    action_type: str
    summary: str
    exact_payload_hash: str
    price_ceiling: Money | None = None
    expires_at: datetime
    status: ApprovalStatus = ApprovalStatus.pending
    approved_at: datetime | None = None
    rejected_at: datetime | None = None


class ApprovalCreateRequest(StrictBaseModel):
    action_type: str
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    price_ceiling: Money | None = None
    expires_in_hours: int = 24


class BookingSimulationRequest(StrictBaseModel):
    action_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    approval_id: str | None = None
    price: Money
    cancellation_policy_acknowledged: bool = False


class BookingRecord(StrictBaseModel):
    booking_id: str
    trip_id: str
    approval_id: str
    action_type: str
    provider_reference: str
    simulated: bool = True
    status: str = "simulated_confirmed"
    price: Money
    created_at: datetime
    notes: list[str] = Field(default_factory=list)
