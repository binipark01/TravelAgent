from __future__ import annotations

from typing import Any

from pydantic import Field

from travel_agent.app.schemas.approvals import ApprovalRequest, BookingRecord
from travel_agent.app.schemas.brief import TripBrief
from travel_agent.app.schemas.budget import BudgetEstimate
from travel_agent.app.schemas.common import (
    AuditEvent,
    CriticFinding,
    SourceRef,
    StrictBaseModel,
    TripStatus,
)
from travel_agent.app.schemas.itinerary import Itinerary
from travel_agent.app.schemas.providers import (
    AccommodationOption,
    FlightOption,
    FxInfo,
    LocalTransportPlan,
    NearbyGuide,
    POIOption,
    SafetyInfo,
    TransportTicketGuide,
    VisaCheckResult,
)


class TripPlanState(StrictBaseModel):
    trip_id: str
    user_id: str | None = None
    locale: str = "ko-KR"
    currency: str = "KRW"
    timezone: str = "Asia/Seoul"
    raw_user_message: str
    raw_user_messages: list[str] = Field(default_factory=list)
    brief: TripBrief | None = None
    user_profile_snapshot: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    destination_candidates: list[str] = Field(default_factory=list)
    selected_destination: str | None = None
    transport_options: list[FlightOption] = Field(default_factory=list)
    accommodation_options: list[AccommodationOption] = Field(default_factory=list)
    poi_candidates: list[POIOption] = Field(default_factory=list)
    activity_options: list[POIOption] = Field(default_factory=list)
    local_transport_options: list[dict[str, Any]] = Field(default_factory=list)
    route_evidence_refs: list[str] = Field(default_factory=list)
    draft_itinerary: Itinerary | None = None
    optimized_itinerary: Itinerary | None = None
    budget: BudgetEstimate | None = None
    risk_findings: list[CriticFinding] = Field(default_factory=list)
    visa_result: VisaCheckResult | None = None
    local_transport: LocalTransportPlan | None = None
    fx_info: FxInfo | None = None
    safety_info: SafetyInfo | None = None
    nearby_guide: NearbyGuide | None = None
    transport_tickets: TransportTicketGuide | None = None
    critic_findings: list[CriticFinding] = Field(default_factory=list)
    approval_requests: list[ApprovalRequest] = Field(default_factory=list)
    booking_records: list[BookingRecord] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    audit_log: list[AuditEvent] = Field(default_factory=list)
    # 대화형 질문("오타루 볼거 뭐있냐")에 LLM이 바로 답한 텍스트(계획 요약 대신 표시).
    assistant_message: str | None = None
    # 사용자가 명시 안 해 기본값으로 추정한 항목(출발지·날짜·인원·예산 등) → 보완 제안용.
    input_suggestions: list[str] = Field(default_factory=list)
    status: TripStatus = TripStatus.intake


class TripCreateRequest(StrictBaseModel):
    message: str
    user_id: str | None = None
    locale: str = "ko-KR"
    currency: str = "KRW"
    timezone: str = "Asia/Seoul"


class TripMessageRequest(StrictBaseModel):
    message: str


class TripSummaryResponse(StrictBaseModel):
    trip_id: str
    status: TripStatus
    summary: str
    missing_fields: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    state: TripPlanState | None = None


class FinalPlanResponse(StrictBaseModel):
    trip_id: str
    status: TripStatus
    summary: str
    assumptions: list[str]
    missing_fields: list[str]
    recommended_destination: str | None
    transport_options: list[FlightOption]
    accommodation_options: list[AccommodationOption]
    itinerary: Itinerary | None
    budget: BudgetEstimate | None
    visa_result: VisaCheckResult | None = None
    local_transport: LocalTransportPlan | None = None
    fx_info: FxInfo | None = None
    safety_info: SafetyInfo | None = None
    nearby_guide: NearbyGuide | None = None
    transport_tickets: TransportTicketGuide | None = None
    risk_findings: list[CriticFinding]
    critic_findings: list[CriticFinding]
    approval_requests: list[ApprovalRequest]
    source_refs: list[SourceRef]
    next_actions: list[str]
