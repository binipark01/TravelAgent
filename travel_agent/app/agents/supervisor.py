from __future__ import annotations

from datetime import date, timedelta

from travel_agent.app.agents.accommodation import AccommodationAgent
from travel_agent.app.agents.budget import BudgetAgent
from travel_agent.app.agents.core_planner import CorePlannerAgent
from travel_agent.app.agents.critic import PlanCriticAgent
from travel_agent.app.agents.destination import DestinationDiscoveryAgent
from travel_agent.app.agents.fx import FxAgent
from travel_agent.app.agents.intake import IntakeAgent
from travel_agent.app.agents.llm_client import (
    CodexTripBriefClient,
    OpenAITripBriefClient,
    codex_brief_available,
)
from travel_agent.app.agents.local_transport import LocalTransportAgent
from travel_agent.app.agents.nearby import NearbyAgent
from travel_agent.app.agents.poi import RestaurantAgent
from travel_agent.app.agents.presentation import PresentationAgent
from travel_agent.app.agents.route_optimizer import RouteAgent
from travel_agent.app.agents.safety import SafetyAgent
from travel_agent.app.agents.transport import FlightAgent
from travel_agent.app.agents.user_profile import UserProfileAgent
from travel_agent.app.agents.visa import VisaAgent
from travel_agent.app.orchestration.agent_recorder import AgentRunRecorder
from travel_agent.app.orchestration.run_context import RunContext
from travel_agent.app.orchestration.state_machine import (
    append_source_refs,
    critical_missing_fields,
    set_status,
)
from travel_agent.app.schemas.common import FindingSeverity, TripStatus
from travel_agent.app.schemas.trip import FinalPlanResponse, TripPlanState


class TravelSupervisorAgent:
    def __init__(self, context: RunContext) -> None:
        providers = context.providers
        self.context = context
        llm_client = None
        if context.settings.enable_live_llm:
            if context.settings.openai_api_key:
                llm_client = OpenAITripBriefClient(
                    api_key=context.settings.openai_api_key,
                    model=context.settings.openai_model,
                )
            elif codex_brief_available(context.settings.codex_cli_command):
                llm_client = CodexTripBriefClient(
                    command=context.settings.codex_cli_command,
                    model=context.settings.codex_oauth_model,
                    timeout_seconds=min(context.settings.codex_oauth_timeout_seconds, 90),
                    reasoning_effort=context.settings.codex_reasoning_effort,
                )
        self.intake_agent = IntakeAgent(
            llm_client=llm_client,
            enable_live_llm=context.settings.enable_live_llm and llm_client is not None,
        )
        self.user_profile_agent = UserProfileAgent()
        self.destination_agent = DestinationDiscoveryAgent()
        self.flight_agent = FlightAgent(
            providers.flights,
            live_enabled=context.settings.enable_flight_source_probes,
            live_timeout=max(context.settings.flight_source_probe_timeout_seconds, 40),
        )
        self.accommodation_agent = AccommodationAgent(
            context.accommodation_search_tool,
            live_enabled=context.settings.enable_flight_source_probes,
            live_timeout=max(context.settings.flight_source_probe_timeout_seconds, 35),
        )
        self.restaurant_agent = RestaurantAgent(
            providers.places,
            live_enabled=context.settings.enable_flight_source_probes,
            live_timeout=max(context.settings.flight_source_probe_timeout_seconds, 35),
        )
        self.route_agent = RouteAgent(providers.routes)
        self.visa_agent = VisaAgent()
        self.local_transport_agent = LocalTransportAgent()
        self.fx_agent = FxAgent()
        self.safety_agent = SafetyAgent()
        self.nearby_agent = NearbyAgent()
        self.budget_agent = BudgetAgent()
        self.critic_agent = PlanCriticAgent()
        self.presentation_agent = PresentationAgent()
        self.core_planner = CorePlannerAgent(
            command=context.settings.codex_cli_command,
            model=context.settings.codex_oauth_model,
            timeout_seconds=min(context.settings.codex_oauth_timeout_seconds, 60),
            enabled=context.settings.enable_live_llm
            and codex_brief_available(context.settings.codex_cli_command),
            reasoning_effort=context.settings.codex_reasoning_effort,
        )

    def run_intake(self, state: TripPlanState, message: str | None = None) -> TripPlanState:
        intake_message = message or state.raw_user_message
        # 마지막 요소가 현재 메시지이므로 그 앞쪽이 이전 대화 이력이다.
        history = [m for m in state.raw_user_messages[:-1] if m and m.strip()]
        result = self.intake_agent.run(
            intake_message,
            currency=state.currency,
            existing_brief=state.brief,
            history=history,
        )
        state.brief = result.brief
        state.missing_fields = result.brief.missing_fields
        state.assumptions = result.brief.assumptions
        status = TripStatus.needs_user_input if state.missing_fields else TripStatus.intake
        set_status(state, status, "Intake completed with parsed travel request.")
        return state

    def _pause_for_critical_missing(
        self, state: TripPlanState, recorder: AgentRunRecorder | None
    ) -> FinalPlanResponse:
        missing = critical_missing_fields(state)
        set_status(state, TripStatus.needs_user_input, "Agent run paused for missing fields.")
        if recorder:
            recorder.event(
                "missing_info_detected",
                "필수 여행 정보가 부족해 agent run이 대기 중입니다.",
                {"missing_fields": missing},
            )
        return self.presentation_agent.build_final_response(state)

    def run_agent_workflow(
        self,
        state: TripPlanState,
        *,
        message: str | None = None,
        recorder: AgentRunRecorder | None = None,
    ) -> FinalPlanResponse:
        self._recorded_step(
            recorder,
            "IntakeAgent",
            "요청 분석",
            lambda: self.run_intake(state, message=message),
            lambda: self._intake_summary(state),
        )
        # 후속 질문 없이 항상 진행: 비어 있는 필드는 조용히 기본값으로 채운다.
        self._ensure_minimum_brief(state)
        state.missing_fields = []
        state.critic_findings = []
        set_status(state, TripStatus.researching, "Agent research stage started.")
        self.user_profile_agent.run(state)

        # 목적지는 모든 하위 작업의 전제이므로 항상 먼저 확정한다.
        self._recorded_step(
            recorder,
            "DestinationDiscoveryAgent",
            "목적지 후보 탐색",
            lambda: self.destination_agent.run(state),
            lambda: (
                f"{len(state.destination_candidates)}개 후보, 선택: {state.selected_destination}"
            ),
        )

        # 코어 오케스트레이터가 요청에 맞는 서브에이전트 집합을 동적으로 선택한다.
        plan = self.core_planner.plan(state)
        selected = self._expand_dependencies(plan.agents)
        if recorder:
            recorder.event(
                "core_plan_decided",
                f"코어 에이전트가 서브에이전트 {len(selected)}개를 선택했습니다: "
                f"{', '.join(selected) or '없음'} ({plan.source})",
                {"agents": selected, "reason": plan.reason, "source": plan.source},
            )

        set_status(state, TripStatus.drafting, "Agent itinerary stage started.")
        if "flight" in selected:
            self._recorded_step(
                recorder,
                "FlightAgent",
                "항공/이동 후보 탐색",
                lambda: self.flight_agent.run(state),
                lambda: f"{len(state.transport_options)}개 항공/이동 후보",
                [{"tool": "FlightProvider.search_flights", "count": len(state.transport_options)}],
            )
        if "accommodation" in selected:
            self._recorded_step(
                recorder,
                "AccommodationAgent",
                "숙소 후보 탐색",
                lambda: self.accommodation_agent.run(state),
                lambda: f"{len(state.accommodation_options)}개 숙소 후보",
                [
                    {
                        "tool": "AccommodationSearchTool.search",
                        "count": len(state.accommodation_options),
                    }
                ],
            )
        if "restaurant" in selected:
            self._recorded_step(
                recorder,
                "RestaurantAgent",
                "맛집/쇼핑/체험 후보 탐색",
                lambda: self.restaurant_agent.run(state),
                lambda: f"{len(state.poi_candidates)}개 후보",
                [{"tool": "PlacesProvider.search_pois", "count": len(state.poi_candidates)}],
            )
        if "route" in selected:
            self._recorded_step(
                recorder,
                "RouteAgent",
                "동선 최적화",
                lambda: self.route_agent.run(state),
                lambda: (
                    f"{len(state.optimized_itinerary.days) if state.optimized_itinerary else 0}"
                    "일 일정"
                ),
                [{"tool": "RoutesProvider.compute_route_matrix"}],
            )
        if "budget" in selected:
            self._recorded_step(
                recorder,
                "BudgetAgent",
                "예산 계산",
                lambda: self.budget_agent.run(state),
                lambda: (
                    f"총 예상 비용 {state.budget.total_estimated_cost:.0f} {state.currency}"
                    if state.budget
                    else "예산 계산 없음"
                ),
            )
        # 항상 실행하는 횡단 정보(입국/비자, 현지 이동) — LLM 선택과 무관한 해외여행 필수 정보
        self._recorded_step(
            recorder,
            "VisaAgent",
            "입국/비자 요건 확인",
            lambda: self.visa_agent.run(state),
            lambda: (
                state.visa_result.summary if state.visa_result else "입국 요건 정보 없음"
            ),
        )
        self._recorded_step(
            recorder,
            "LocalTransportAgent",
            "현지 교통 안내",
            lambda: self.local_transport_agent.run(state),
            lambda: (
                f"{state.local_transport.city} 교통 안내"
                if state.local_transport
                else "현지 교통 데이터 없음"
            ),
        )
        self._recorded_step(
            recorder,
            "FxAgent",
            "환율/예산 환산",
            lambda: self.fx_agent.run(state),
            lambda: (
                f"1 {state.fx_info.target_currency} ≈ {state.fx_info.base_per_target:.2f} "
                f"{state.fx_info.base_currency}"
                if state.fx_info
                else "환율 정보 없음"
            ),
        )
        self._recorded_step(
            recorder,
            "SafetyAgent",
            "안전·긴급 정보",
            lambda: self.safety_agent.run(state),
            lambda: (
                f"{state.safety_info.destination_country} 안전 정보"
                if state.safety_info
                else "안전 정보 데이터 없음"
            ),
        )
        self._recorded_step(
            recorder,
            "NearbyAgent",
            "근교 당일치기 정리",
            lambda: self.nearby_agent.run(state),
            lambda: (
                f"{state.nearby_guide.hub} 근교 {len(state.nearby_guide.destinations)}곳"
                if state.nearby_guide
                else "근교 데이터 없음"
            ),
        )
        self._collect_provider_source_refs(state)

        set_status(state, TripStatus.validating, "Agent validation stage started.")
        self._recorded_step(
            recorder,
            "PlanCriticAgent",
            "일정 검증",
            lambda: self.critic_agent.run(state),
            lambda: f"{len(state.critic_findings)}개 검증 결과",
        )
        set_status(state, TripStatus.ready, "Agent run completed.")
        response = self._recorded_step(
            recorder,
            "PresentationAgent",
            "최종 계획 정리",
            lambda: self.presentation_agent.build_final_response(state),
            lambda: "최종 계획 응답 정리 완료",
        )
        if recorder:
            recorder.event("plan_ready", "여행 계획이 준비되었습니다.", {"trip_id": state.trip_id})
        return response

    def _ensure_minimum_brief(self, state: TripPlanState) -> None:
        """후속 질문 없이 계획이 항상 완성되도록 빈 필드를 조용히 채운다."""
        brief = state.brief
        if brief is None:
            return
        if not brief.destinations:
            brief.destinations = ["Japan"]
        if not brief.destination_hint:
            brief.destination_hint = ", ".join(brief.destinations)
        if not brief.origin:
            brief.origin = "서울"
        if brief.travelers is None:
            brief.travelers = brief.traveler_count or brief.adults or 1
        brief.traveler_count = brief.traveler_count or brief.travelers
        brief.adults = brief.adults or brief.travelers
        if not brief.start_date:
            days = brief.duration_days or 4
            start = date.today() + timedelta(days=30)
            brief.start_date = start
            brief.end_date = start + timedelta(days=days - 1)
            brief.duration_days = days
            brief.duration_nights = max(days - 1, 0)
        elif not brief.end_date:
            days = brief.duration_days or 4
            brief.end_date = brief.start_date + timedelta(days=days - 1)
            brief.duration_days = days
            brief.duration_nights = max(days - 1, 0)

    def _expand_dependencies(self, agents: list[str]) -> list[str]:
        """선택된 capability에 필요한 선행 작업을 보강하고 의존성 안전 순서로 정렬한다."""
        selected = set(agents)
        if "route" in selected:
            selected.add("restaurant")  # 동선 최적화는 장소(식당 등) 후보가 필요
        order = ["flight", "accommodation", "restaurant", "route", "budget"]
        return [key for key in order if key in selected]

    def run_planning(self, state: TripPlanState) -> FinalPlanResponse:
        self.run_intake(state)
        if critical_missing_fields(state):
            set_status(state, TripStatus.needs_user_input, "Planning paused for missing fields.")
            state.critic_findings = []
            self.critic_agent.run(state)
            return self.presentation_agent.build_final_response(state)

        set_status(state, TripStatus.researching, "Research stage started.")
        self.user_profile_agent.run(state)
        self.destination_agent.run(state)
        self.flight_agent.run(state)
        self.accommodation_agent.run(state)
        self.restaurant_agent.run(state)
        self._collect_provider_source_refs(state)

        set_status(state, TripStatus.drafting, "Draft itinerary stage started.")
        self.route_agent.run(state)
        self.visa_agent.run(state)
        self.local_transport_agent.run(state)

        self.budget_agent.run(state)
        self.fx_agent.run(state)
        self.safety_agent.run(state)
        self.nearby_agent.run(state)
        set_status(state, TripStatus.validating, "Validation stage started.")
        self.critic_agent.run(state)
        blocking = [f for f in state.critic_findings if f.severity == FindingSeverity.blocking]
        if blocking:
            set_status(state, TripStatus.needs_user_input, "Planning has blocking findings.")
        else:
            set_status(state, TripStatus.ready, "Planning completed.")
        return self.presentation_agent.build_final_response(state)

    def validate(self, state: TripPlanState) -> TripPlanState:
        self.critic_agent.run(state)
        return state

    def _collect_provider_source_refs(self, state: TripPlanState) -> None:
        refs = []
        refs.extend(option.metadata.source_ref for option in state.transport_options)
        refs.extend(option.metadata.source_ref for option in state.accommodation_options)
        refs.extend(poi.metadata.source_ref for poi in state.poi_candidates)
        append_source_refs(state, refs)

    def _is_flight_search_request(self, state: TripPlanState) -> bool:
        if not state.brief:
            return False
        return "flight_search" in (state.brief.transport_preference or "")

    def _is_accommodation_search_request(self, state: TripPlanState) -> bool:
        if not state.brief:
            return False
        text = f"{state.raw_user_message}\n{' '.join(state.raw_user_messages)}".lower()
        wants_accommodation = any(
            token in text
            for token in ["숙소", "호텔", "에어비앤비", "airbnb", "agoda", "booking.com"]
        )
        wants_full_plan = any(
            token in text for token in ["일정", "여행 계획", "동선", "맛집", "쇼핑", "관광", "코스"]
        )
        return (
            wants_accommodation
            and not wants_full_plan
            and not self._is_flight_search_request(state)
        )

    def _finish_flight_search(
        self, state: TripPlanState, recorder: AgentRunRecorder | None
    ) -> FinalPlanResponse:
        self._collect_provider_source_refs(state)
        set_status(state, TripStatus.validating, "Flight search validation stage started.")
        self._recorded_step(
            recorder,
            "PlanCriticAgent",
            "항공 후보 검증",
            lambda: self.critic_agent.run(state),
            lambda: f"{len(state.critic_findings)}개 검증 결과",
        )
        blocking = [f for f in state.critic_findings if f.severity == FindingSeverity.blocking]
        if blocking:
            set_status(state, TripStatus.needs_user_input, "Flight search needs user input.")
            if recorder:
                recorder.event(
                    "critic_blocker_found",
                    "항공 후보 확인 중 차단 이슈가 발견되었습니다.",
                    {"count": len(blocking)},
                )
        else:
            set_status(state, TripStatus.ready, "Flight search completed.")

        response = self._recorded_step(
            recorder,
            "PresentationAgent",
            "항공 후보 정리",
            lambda: self.presentation_agent.build_final_response(state),
            lambda: "항공 후보 응답 정리 완료",
        )
        if recorder and state.status == TripStatus.ready:
            recorder.event("plan_ready", "항공 후보가 준비되었습니다.", {"trip_id": state.trip_id})
        return response

    def _finish_accommodation_search(
        self, state: TripPlanState, recorder: AgentRunRecorder | None
    ) -> FinalPlanResponse:
        self._collect_provider_source_refs(state)
        set_status(state, TripStatus.validating, "Accommodation search validation stage started.")
        self._recorded_step(
            recorder,
            "PlanCriticAgent",
            "숙소 후보 검증",
            lambda: self.critic_agent.run(state),
            lambda: f"{len(state.critic_findings)}개 검증 결과",
        )
        blocking = [f for f in state.critic_findings if f.severity == FindingSeverity.blocking]
        if blocking:
            set_status(state, TripStatus.needs_user_input, "Accommodation search needs user input.")
            if recorder:
                recorder.event(
                    "critic_blocker_found",
                    "숙소 후보 확인 중 차단 이슈가 발견되었습니다.",
                    {"count": len(blocking)},
                )
        else:
            set_status(state, TripStatus.ready, "Accommodation search completed.")

        response = self._recorded_step(
            recorder,
            "PresentationAgent",
            "숙소 후보 정리",
            lambda: self.presentation_agent.build_final_response(state),
            lambda: "숙소 후보 응답 정리 완료",
        )
        if recorder and state.status == TripStatus.ready:
            recorder.event("plan_ready", "숙소 후보가 준비되었습니다.", {"trip_id": state.trip_id})
        return response

    def _recorded_step(
        self,
        recorder: AgentRunRecorder | None,
        agent_name: str,
        input_summary: str,
        action,
        output_summary,
        tool_calls: list[dict] | None = None,
    ):
        step_id = recorder.start_step(agent_name, input_summary) if recorder else None
        try:
            result = action()
            if recorder and step_id:
                recorder.complete_step(step_id, output_summary(), tool_calls=tool_calls)
            return result
        except Exception as exc:
            if recorder and step_id:
                recorder.fail_step(step_id, str(exc))
            raise

    def _intake_summary(self, state: TripPlanState) -> str:
        if not state.brief:
            return "요청 분석 결과 없음"
        destinations = ", ".join(state.brief.destinations) or "목적지 미정"
        return (
            f"목적지: {destinations}, 인원: {state.brief.travelers or '미정'}, "
            f"누락: {len(state.missing_fields)}개"
        )

    def _add_agent_passport_missing(self, state: TripPlanState) -> None:
        if not state.brief or not state.brief.destinations:
            return
        if self._is_accommodation_search_request(state):
            state.missing_fields = [
                field
                for field in state.missing_fields
                if field not in {"origin", "passport_country"}
            ]
            state.brief.missing_fields = [
                field
                for field in state.brief.missing_fields
                if field not in {"origin", "passport_country"}
            ]
            return
        if self._is_flight_search_request(state):
            state.missing_fields = [
                field for field in state.missing_fields if field != "passport_country"
            ]
            state.brief.missing_fields = [
                field for field in state.brief.missing_fields if field != "passport_country"
            ]
            return
        if state.brief.passport_country:
            state.missing_fields = [
                field for field in state.missing_fields if field != "passport_country"
            ]
            state.brief.missing_fields = [
                field for field in state.brief.missing_fields if field != "passport_country"
            ]
            return
        if "passport_country" not in state.missing_fields:
            state.missing_fields.append("passport_country")
        if "passport_country" not in state.brief.missing_fields:
            state.brief.missing_fields.append("passport_country")

    def _skip_remaining_after_intake(self, recorder: AgentRunRecorder | None, reason: str) -> None:
        if not recorder:
            return
        for agent_name in [
            "DestinationDiscoveryAgent",
            "FlightAgent",
            "AccommodationAgent",
            "RestaurantAgent",
            "RouteAgent",
            "BudgetAgent",
            "PlanCriticAgent",
            "PresentationAgent",
        ]:
            recorder.skip_step(agent_name, reason)
