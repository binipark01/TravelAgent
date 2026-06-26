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
    LocalEventsGuide,
    LocalTransportPlan,
    MultiCityPlan,
    NearbyGuide,
    POIOption,
    PrepChecklist,
    SafetyInfo,
    StayAreaGuide,
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
    stay_area_guide: StayAreaGuide | None = None
    prep_checklist: PrepChecklist | None = None
    multicity_plan: MultiCityPlan | None = None
    local_events: LocalEventsGuide | None = None
    transport_tickets: TransportTicketGuide | None = None
    critic_findings: list[CriticFinding] = Field(default_factory=list)
    approval_requests: list[ApprovalRequest] = Field(default_factory=list)
    booking_records: list[BookingRecord] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    audit_log: list[AuditEvent] = Field(default_factory=list)
    # 대화형 질문("오타루 볼거 뭐있냐")에 LLM이 바로 답한 텍스트(계획 요약 대신 표시).
    assistant_message: str | None = None
    # 정보가 부족할 때 '무엇을 알려주면 더 정확해지는지' 제안 문장(LLM 우선, 규칙 기반 폴백).
    clarification: str | None = None
    status: TripStatus = TripStatus.intake

    @property
    def primary_destination(self) -> str | None:
        """일정·횡단정보의 기준 도시. 선택된 목적지 우선, 없으면 brief 첫 후보.

        13곳에 흩어져 있던 `selected_destination or (brief.destinations[0] ...)` 보일러플레이트를
        한 곳으로 모아, 멀티시티/도시전환 규칙이 바뀌어도 여기만 고치면 되게 한다.
        property라 Pydantic 필드가 아니어서 직렬화(응답 shape)에 영향 없다.
        """
        if self.selected_destination:
            return self.selected_destination
        if self.brief and self.brief.destinations:
            return self.brief.destinations[0]
        return None


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
    stay_area_guide: StayAreaGuide | None = None
    prep_checklist: PrepChecklist | None = None
    multicity_plan: MultiCityPlan | None = None
    local_events: LocalEventsGuide | None = None
    transport_tickets: TransportTicketGuide | None = None
    risk_findings: list[CriticFinding]
    critic_findings: list[CriticFinding]
    approval_requests: list[ApprovalRequest]
    source_refs: list[SourceRef]
    next_actions: list[str]
