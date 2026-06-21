from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

from travel_agent.app.agent_core.cancellation import RunCancelled, is_cancelled
from travel_agent.app.agents.accommodation import AccommodationAgent
from travel_agent.app.agents.budget import BudgetAgent
from travel_agent.app.agents.checklist import ChecklistAgent
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
from travel_agent.app.agents.multicity import MultiCityAgent
from travel_agent.app.agents.nearby import NearbyAgent
from travel_agent.app.agents.poi import RestaurantAgent
from travel_agent.app.agents.presentation import PresentationAgent
from travel_agent.app.agents.route_optimizer import RouteAgent
from travel_agent.app.agents.safety import SafetyAgent
from travel_agent.app.agents.stay_area import StayAreaAgent
from travel_agent.app.agents.transport import FlightAgent
from travel_agent.app.agents.transport_tickets import TransportTicketsAgent
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
        self.stay_area_agent = StayAreaAgent()
        self.checklist_agent = ChecklistAgent()
        self.multicity_agent = MultiCityAgent()
        self.transport_tickets_agent = TransportTicketsAgent()
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
        # 이어가기 발화가 '다른 도시'를 말하면 목적지를 전환하고 이전 결과를 비운다.
        self._apply_destination_switch(state)
        state.missing_fields = state.brief.missing_fields
        state.assumptions = state.brief.assumptions
        status = TripStatus.needs_user_input if state.missing_fields else TripStatus.intake
        set_status(state, status, "Intake completed with parsed travel request.")
        return state

    def _apply_destination_switch(self, state: TripPlanState) -> None:
        """이어가기에서 다른 도시로 바뀌면 목적지를 전환한다(LLM이 뽑은 brief 기준).

        intake가 최신 요청의 목적지로 brief.destinations를 교체하므로(시즈오카·나고야 등
        하드코딩 목록에 없는 도시도 인식), 현재 선택이 거기 없으면 전환으로 본다. 전환 시
        selected_destination을 비워(목적지 에이전트가 재선택) 이전 도시 결과를 모두
        무효화한다 → 시즈오카를 요청했는데 삿포로가 남지 않게.
        """
        brief = state.brief
        current = state.selected_destination
        if brief is None or not current:
            return  # 첫 계획이면 일반 흐름(목적지 에이전트가 선택)
        # 나라(일본)만 있는 모호한 목적지는 전환 판단에서 제외(이미 도시로 해석됨).
        specific = [
            dest
            for dest in brief.destinations
            if dest.split(",")[0].strip().lower() != "japan"
        ]
        if not specific:
            return
        if any(self._same_city(current, dest) for dest in specific):
            return  # 현재 목적지가 여전히 후보 → 유지(편집/보완 턴)
        # 다른 도시로 전환: 선택을 비워 재선택 + 이전 도시 결과 무효화.
        brief.selected_destination = None
        state.selected_destination = None
        # 이전 도시에 묶인 편집·안내 입력도 비운다 — intake가 must_include 등을 턴 사이에
        # 보존해, 히로시마의 '미야지마 꼭 넣어줘'가 파리 일정에 남는 일을 막는다.
        brief.must_include = []
        brief.must_avoid = []
        brief.clarification = None
        self._reset_destination_bound_results(state)

    @staticmethod
    def _same_city(a: str, b: str) -> bool:
        """표기 차이를 무시하고 같은 도시인지(첫 구간 비교: 'Tokyo, Japan'→'tokyo')."""
        return a.split(",")[0].strip().lower() == b.split(",")[0].strip().lower()

    @staticmethod
    def _reset_destination_bound_results(state: TripPlanState) -> None:
        """목적지 변경 시 이전 도시에 묶인 후보·일정·횡단정보를 모두 비운다."""
        state.transport_options = []
        state.accommodation_options = []
        state.poi_candidates = []
        state.activity_options = []
        state.local_transport_options = []
        state.draft_itinerary = None
        state.optimized_itinerary = None
        state.budget = None
        state.visa_result = None
        state.local_transport = None
        state.fx_info = None
        state.safety_info = None
        state.nearby_guide = None
        state.stay_area_guide = None
        state.prep_checklist = None
        state.multicity_plan = None
        state.transport_tickets = None
        # 재검색 판정용 도메인 서명 캐시도 비워 확실히 다시 검색하게 한다.
        for key in ("flight_sig", "accommodation_sig", "restaurant_sig"):
            state.constraints.pop(key, None)

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
        # 이어가기 턴에 '이미 일정이 있는 종합 계획'이면 편집/제약이 항상 재반영되도록
        # 일정·예산을 강제 재구성한다. 항공권만/숙소만 같은 단일 검색 세션은 건드리지 않는다.
        if state.optimized_itinerary is not None:
            selected = self._expand_dependencies([*selected, "route", "budget"])
        # 횡단 정보(비자·환율·안전·근교·교통권)는 '종합 계획'일 때만. 단일 검색은 과함.
        is_full_plan = "route" in selected
        if recorder:
            recorder.event(
                "core_plan_decided",
                f"코어 에이전트가 서브에이전트 {len(selected)}개를 선택했습니다: "
                f"{', '.join(selected) or '없음'} ({plan.source})",
                {"agents": selected, "reason": plan.reason, "source": plan.source},
            )

        set_status(state, TripStatus.drafting, "Agent itinerary stage started.")
        # 항공·숙소·식당은 서로 독립(다른 state 필드 기록)이라 동시에 검색한다 — 가장 느린
        # 단계(브라우저 스크래핑·웹검색)들이 합쳐지지 않고 겹쳐 돈다. 재검색 판정은 메인스레드
        # 에서 먼저 한다(state.constraints 기록이 직렬이어야 안전).
        core_specs: list = []
        if "flight" in selected:
            if self._needs_search(state, "flight", bool(state.transport_options)):
                core_specs.append((
                    "FlightAgent",
                    "항공/이동 후보 탐색",
                    lambda: self.flight_agent.run(state),
                    lambda: f"{len(state.transport_options)}개 항공/이동 후보",
                    lambda: [{"tool": "FlightProvider.search_flights",
                              "count": len(state.transport_options)}],
                ))
            else:
                self._emit_reused(recorder, "항공", len(state.transport_options))
        if "accommodation" in selected:
            if self._needs_search(state, "accommodation", bool(state.accommodation_options)):
                core_specs.append((
                    "AccommodationAgent",
                    "숙소 후보 탐색",
                    lambda: self.accommodation_agent.run(state),
                    lambda: f"{len(state.accommodation_options)}개 숙소 후보",
                    lambda: [{"tool": "AccommodationSearchTool.search",
                              "count": len(state.accommodation_options)}],
                ))
            else:
                self._emit_reused(recorder, "숙소", len(state.accommodation_options))
        if "restaurant" in selected:
            if self._needs_search(state, "restaurant", bool(state.poi_candidates)):
                core_specs.append((
                    "RestaurantAgent",
                    "맛집/쇼핑/체험 후보 탐색",
                    lambda: self.restaurant_agent.run(state),
                    lambda: f"{len(state.poi_candidates)}개 후보",
                    lambda: [{"tool": "PlacesProvider.search_pois",
                              "count": len(state.poi_candidates)}],
                ))
            else:
                self._emit_reused(recorder, "맛집/관광", len(state.poi_candidates))
        self._run_parallel(recorder, core_specs)
        # 동선·예산은 위 결과(관광지·항공·숙소)에 의존하므로 직렬로 둔다.
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
        # 횡단 정보(입국/비자·현지교통·환율·안전·근교·교통권)는 종합 계획일 때만.
        # 항공권만/숙소만 같은 단일 검색에는 붙이지 않는다(과한 출력 방지).
        if is_full_plan:
            # 1차: 서로 독립인 횡단 정보(비자·교통·환율·안전·근교·숙박구역·멀티시티)를 동시에.
            # 각각 다른 state 필드만 기록하므로 충돌 없음. 가장 느린 건 근교·숙박구역 웹검색.
            self._run_parallel(recorder, [
                (
                    "VisaAgent", "입국/비자 요건 확인",
                    lambda: self.visa_agent.run(state),
                    lambda: (
                        state.visa_result.summary if state.visa_result else "입국 요건 정보 없음"
                    ),
                    None,
                ),
                (
                    "LocalTransportAgent", "현지 교통 안내",
                    lambda: self.local_transport_agent.run(state),
                    lambda: (
                        f"{state.local_transport.city} 교통 안내"
                        if state.local_transport else "현지 교통 데이터 없음"
                    ),
                    None,
                ),
                (
                    "FxAgent", "환율/예산 환산",
                    lambda: self.fx_agent.run(state),
                    lambda: (
                        f"1 {state.fx_info.target_currency} ≈ {state.fx_info.base_per_target:.2f} "
                        f"{state.fx_info.base_currency}"
                        if state.fx_info else "환율 정보 없음"
                    ),
                    None,
                ),
                (
                    "SafetyAgent", "안전·긴급 정보",
                    lambda: self.safety_agent.run(state),
                    lambda: (
                        f"{state.safety_info.destination_country} 안전 정보"
                        if state.safety_info else "안전 정보 데이터 없음"
                    ),
                    None,
                ),
                (
                    "NearbyAgent", "근교 당일치기 정리",
                    lambda: self.nearby_agent.run(state),
                    lambda: (
                        f"{state.nearby_guide.hub} 근교 {len(state.nearby_guide.destinations)}곳"
                        if state.nearby_guide else "근교 데이터 없음"
                    ),
                    None,
                ),
                (
                    "StayAreaAgent", "추천 숙박 구역 정리",
                    lambda: self.stay_area_agent.run(state),
                    lambda: (
                        f"{state.stay_area_guide.destination} 숙박 구역 "
                        f"{len(state.stay_area_guide.areas)}곳"
                        if state.stay_area_guide else "숙박 구역 데이터 없음"
                    ),
                    None,
                ),
                (
                    "MultiCityAgent", "멀티시티 동선 정리",
                    lambda: self.multicity_agent.run(state),
                    lambda: (
                        f"{len(state.multicity_plan.segments)}개 도시 동선"
                        if state.multicity_plan else "단일 목적지"
                    ),
                    None,
                ),
            ])
            # 2차: 1차 결과에 의존 — 체크리스트(비자·환율 맥락), 교통권(근교 목적지). 둘은 서로
            # 독립이라 동시에.
            self._run_parallel(recorder, [
                (
                    "ChecklistAgent", "출발 전 준비물 정리",
                    lambda: self.checklist_agent.run(state),
                    lambda: (
                        f"{state.prep_checklist.destination} 준비물 "
                        f"{len(state.prep_checklist.groups)}개 그룹"
                        if state.prep_checklist else "준비물 데이터 없음"
                    ),
                    None,
                ),
                (
                    "TransportTicketsAgent", "교통권 예매·경로 정리",
                    lambda: self.transport_tickets_agent.run(state),
                    lambda: (
                        f"{len(state.transport_tickets.platforms)}개 예매처"
                        if state.transport_tickets else "교통권 데이터 없음"
                    ),
                    None,
                ),
            ])
        # 예산은 FX보다 먼저 돌아 현지통화 환산을 못 채운다 → FX 완료 후 여기서 보강.
        if state.budget and state.fx_info and not state.budget.total_local_label:
            state.budget.total_local_label = BudgetAgent._local_total(
                state.budget.total_estimated_cost, state
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
        """후속 질문 없이 계획이 항상 완성되도록 빈 필드를 조용히 채운다.

        대신 사용자가 명시하지 않아 기본값으로 추정한 항목을 input_suggestions에 남겨
        '이걸 알려주면 더 정확해진다'고 제안할 수 있게 한다.
        """
        brief = state.brief
        if brief is None:
            return
        # 보완 제안: LLM(intake)이 써준 문장을 우선 쓰고, 없으면 빈 필드로 규칙 기반 문장.
        if brief.clarification and brief.clarification.strip():
            state.clarification = brief.clarification.strip()
        else:
            missing: list[str] = []
            if not brief.origin:
                missing.append("출발지")
            if not brief.start_date:
                missing.append("출발 날짜")
            if brief.travelers is None and not brief.traveler_count and not brief.adults:
                missing.append("인원")
            if brief.budget_total is None and brief.budget_per_person is None:
                missing.append("예산")
            if not brief.must_include:
                missing.append("관심사(맛집·쇼핑·관광 등)")
            state.clarification = (
                f"{' · '.join(missing)}을(를) 알려주시면 더 정확히 맞춰드려요."
                if missing
                else None
            )
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

    def _has_prior_results(self, state: TripPlanState) -> bool:
        """이어가기 턴인지(이미 검색/일정 결과가 있는지) 판단한다."""
        return bool(
            state.transport_options
            or state.accommodation_options
            or state.poi_candidates
            or state.activity_options
            or state.optimized_itinerary
        )

    def _domain_sig(self, state: TripPlanState, domain: str) -> str:
        """도메인별 '검색 입력' 서명. 이게 같으면 재검색 없이 기존 결과를 재사용한다.

        편집 신호(must_avoid·pace)는 서명에 넣지 않는다 → 편집은 재검색을 유발하지
        않고 RouteAgent가 기존 후보에 적용한다. 반대로 맛집 위주(must_include)·직항
        (transport_preference) 등 검색 결과를 바꾸는 변경은 서명이 바뀌어 재검색된다.
        """
        brief = state.brief
        if not brief:
            return ""
        destination = state.selected_destination or (
            brief.destinations[0] if brief.destinations else None
        )

        def join(*parts) -> str:
            return "|".join("" if part is None else str(part) for part in parts)

        if domain == "flight":
            return join(
                brief.origin, destination, brief.start_date, brief.end_date,
                brief.travelers, brief.transport_preference,
            )
        if domain == "accommodation":
            return join(
                destination, brief.start_date, brief.end_date, brief.travelers,
                brief.accommodation_preference, brief.budget_per_person, brief.budget_total,
            )
        if domain == "restaurant":
            return join(destination, tuple(sorted(brief.must_include or [])))
        return ""

    def _needs_search(self, state: TripPlanState, domain: str, have_results: bool) -> bool:
        """검색 입력이 바뀌었거나 아직 결과가 없으면 True(재검색), 아니면 False(재사용)."""
        sig = self._domain_sig(state, domain)
        key = f"{domain}_sig"
        changed = state.constraints.get(key) != sig
        state.constraints[key] = sig
        return changed or not have_results

    def _emit_reused(self, recorder: AgentRunRecorder | None, label: str, count: int) -> None:
        if recorder:
            recorder.event(
                "search_reused",
                f"{label} 후보를 이전 결과에서 재사용했습니다(입력 변경 없음).",
                {"count": count},
            )

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
        self.transport_tickets_agent.run(state)
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
        self._check_cancel(recorder)
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

    @staticmethod
    def _check_cancel(recorder: AgentRunRecorder | None) -> None:
        """사용자가 중지를 요청했으면 단계 시작 전에 파이프라인을 빠져나온다(협조적 취소)."""
        if is_cancelled(getattr(recorder, "run_id", None)):
            raise RunCancelled()

    def _run_parallel(self, recorder: AgentRunRecorder | None, specs: list) -> None:
        """서로 독립인 에이전트 작업들을 동시에 실행한다(가장 느린 단계의 벽시계 단축).

        작업(action)만 스레드로 병렬 실행하고, 기록(start/complete/fail)은 메인스레드에서
        직렬로 한다 — SQLAlchemy 세션·recorder가 스레드-안전이 아니기 때문. 한 작업이 실패해도
        나머지는 유지(부가 정보 실패로 전체 계획을 죽이지 않는다). 각 spec은
        (이름, 입력요약, action, 출력요약fn, tool_calls_fn|None).
        """
        runnable = [s for s in specs if s is not None]
        if not runnable:
            return
        self._check_cancel(recorder)
        step_ids = [recorder.start_step(s[0], s[1]) if recorder else None for s in runnable]
        errors: list[Exception | None] = [None] * len(runnable)
        with ThreadPoolExecutor(max_workers=len(runnable)) as executor:
            futures = {executor.submit(s[2]): i for i, s in enumerate(runnable)}
            for future in as_completed(futures):
                index = futures[future]
                try:
                    future.result()
                except Exception as exc:  # noqa: BLE001 - 부가 작업 실패는 격리해 둔다
                    errors[index] = exc
        for index, spec in enumerate(runnable):
            step_id = step_ids[index]
            if not (recorder and step_id):
                continue
            _name, _inp, _action, output_summary, tool_calls = spec
            if errors[index] is not None:
                recorder.fail_step(step_id, str(errors[index]))
            else:
                recorder.complete_step(
                    step_id, output_summary(), tool_calls=tool_calls() if tool_calls else None
                )

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
