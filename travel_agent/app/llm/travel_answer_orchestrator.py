from __future__ import annotations

from dataclasses import dataclass

from travel_agent.app.agents.intake import IntakeAgent
from travel_agent.app.config import Settings
from travel_agent.app.llm.accommodation_search_context import (
    build_accommodation_answer_context,
    build_trip_plan_state_for_answer,
)
from travel_agent.app.llm.flight_search_context import build_flight_search_answer_context
from travel_agent.app.llm.flight_source_probe import (
    FlightSourceProbeRunner,
    PublicFlightSourceProbeRunner,
)
from travel_agent.app.schemas.brief import TripBrief
from travel_agent.app.schemas.llm import DomainAgentRun, FlightSearchAnswerContext
from travel_agent.app.schemas.trip import TripPlanState
from travel_agent.app.tools.accommodation_search import AccommodationSearchTool


@dataclass(frozen=True)
class CoreTravelAnswerOrchestrator:
    settings: Settings
    flight_probe_runner: FlightSourceProbeRunner | None = None
    accommodation_tool: AccommodationSearchTool | None = None
    intake_agent: IntakeAgent | None = None

    def build_context(
        self,
        *,
        message: str,
        locale: str,
        currency: str,
        timezone: str,
    ) -> FlightSearchAnswerContext:
        intake_agent = self.intake_agent or IntakeAgent()
        intake_result = intake_agent.run(message, currency=currency)
        state = build_trip_plan_state_for_answer(
            message=message,
            locale=locale,
            currency=currency,
            timezone=timezone,
            brief=intake_result.brief,
        )
        contexts = [
            self._flight_context(message=message, currency=currency),
            self._accommodation_context(message=message, state=state),
        ]
        context = merge_answer_contexts(contexts)
        if context.has_content():
            context.agent_runs.insert(
                0,
                DomainAgentRun(
                    agent_name="IntakeAgent",
                    title="요청 분석 agent",
                    status="completed",
                    summary=_intake_summary(intake_result.brief),
                    evidence=intake_result.brief.assumptions,
                ),
            )
        return context

    def _flight_context(self, *, message: str, currency: str) -> FlightSearchAnswerContext:
        if not self.settings.enable_flight_source_probes:
            return FlightSearchAnswerContext()
        runner = self.flight_probe_runner or PublicFlightSourceProbeRunner(
            timeout_seconds=self.settings.flight_source_probe_timeout_seconds
        )
        return build_flight_search_answer_context(
            message=message,
            currency=currency,
            enable_live_probes=self.settings.enable_flight_source_probes,
            probe_runner=runner,
        )

    def _accommodation_context(
        self, *, message: str, state: TripPlanState
    ) -> FlightSearchAnswerContext:
        tool = self.accommodation_tool or AccommodationSearchTool(self.settings)
        return build_accommodation_answer_context(message=message, state=state, tool=tool)


def merge_answer_contexts(
    contexts: list[FlightSearchAnswerContext],
) -> FlightSearchAnswerContext:
    interpreted = [
        context.interpreted_request
        for context in contexts
        if context.interpreted_request
    ]
    source_attempts = [
        attempt
        for context in contexts
        for attempt in context.source_attempts
    ]
    blockers = list(
        dict.fromkeys(
            blocker
            for context in contexts
            for blocker in context.blockers
        )
    )
    agent_runs = [
        agent_run
        for context in contexts
        for agent_run in context.agent_runs
    ]
    return FlightSearchAnswerContext(
        interpreted_request="\n".join(interpreted) if interpreted else None,
        source_attempts=source_attempts,
        blockers=blockers,
        agent_runs=agent_runs,
    )


def travel_answer_prompt(message: str, context: FlightSearchAnswerContext) -> str:
    if not context.has_content():
        return message
    lines = [
        "사용자 원문:",
        message,
        "",
        "core orchestrator가 실행한 하위 agent 결과:",
    ]
    if context.interpreted_request:
        lines.append("- 해석된 요청:")
        lines.extend(f"  - {line}" for line in context.interpreted_request.splitlines())
    for agent_run in context.agent_runs:
        lines.append(
            f"- {agent_run.title}: status={agent_run.status}; summary={agent_run.summary}"
        )
        for evidence in agent_run.evidence:
            lines.append(f"  - evidence: {evidence}")
    if context.source_attempts:
        lines.append("")
        lines.append("검색 출처 및 후보:")
    for attempt in context.source_attempts:
        lines.append(
            f"- domain={attempt.domain}; agent={attempt.agent_name}; "
            f"title={attempt.title}; status={attempt.status}; "
            f"url={attempt.source_url or '없음'}; summary={attempt.summary}"
        )
        for evidence in attempt.evidence:
            lines.append(f"  - evidence: {evidence}")
        for option in attempt.fare_options:
            inbound = (
                f"{option.inbound_departure or '없음'}"
                f"->{option.inbound_arrival or '없음'}"
            )
            lines.append(
                f"  - 후보: {option.airline}; "
                f"가는 편 {option.outbound_departure}->{option.outbound_arrival}; "
                f"오는 편 {inbound}; "
                f"가격 {option.price}; 경유 {option.stops or '미확인'}"
            )
            for note in option.notes:
                lines.append(f"    - note: {note}")
    if context.blockers:
        lines.append("")
        lines.append("제한 사항:")
        lines.extend(f"- {blocker}" for blocker in context.blockers)
    lines.extend(
        [
            "",
            "답변 규칙:",
            "- 실행한 agent 결과와 출처 근거를 우선 사용한다.",
            "- 실제 운임, 객실 재고, 예약 가능 여부는 출처 근거 없이 만들지 않는다.",
            "- 검색 출처 및 후보 목록에 없는 항공편, 호텔명, 가격, URL을 새로 추가하지 않는다.",
            "- 항공권 후보가 없으면 검색 방법을 답변처럼 포장하지 말고 "
            "후보 없음과 필요한 다음 실행만 말한다.",
            "- mock 또는 시뮬레이션 결과는 실제 예약 가능한 상품처럼 말하지 않는다.",
            "- 시뮬레이션 숙소 후보만 있으면 실제 숙소 후보가 아니라 MVP 예시라고 말한다.",
            "- 사용자가 바로 확인할 수 있도록 검색 조건과 출처 URL을 제시한다.",
        ]
    )
    return "\n".join(lines)


def link_only_flight_blocked_answer(context: FlightSearchAnswerContext) -> str | None:
    flight_attempts = [
        attempt for attempt in context.source_attempts if attempt.domain == "flights"
    ]
    if not flight_attempts:
        return None
    if any(attempt.fare_options_found for attempt in flight_attempts):
        return None
    if not any(
        "실시간 항공권 후보" in blocker or "항공권 후보" in blocker
        for blocker in context.blockers
    ):
        return None

    lines = [
        "항공권 후보를 아직 찾지 못했습니다.",
        "",
        "확인한 내용:",
    ]
    lines.extend(
        f"- {attempt.title}: {attempt.summary}" for attempt in flight_attempts
    )
    lines.extend(
        [
            "",
            "다음 실행:",
            "- 브라우저 기반 항공권 검색 agent가 실제 화면에서 가격/시간 후보를 추출해야 합니다.",
            "- 또는 항공권 재고 API 연결이 필요합니다.",
            "",
            "현재 상태에서는 항공편명, 가격, 좌석, 예약 가능 여부를 추천처럼 말하지 않겠습니다.",
        ]
    )
    return "\n".join(lines)


def _intake_summary(brief: TripBrief) -> str:
    destinations = ", ".join(brief.destinations) if brief.destinations else "목적지 미정"
    date_range = "날짜 미정"
    if brief.start_date and brief.end_date:
        date_range = f"{brief.start_date.isoformat()} ~ {brief.end_date.isoformat()}"
    return f"목적지: {destinations}; 기간: {date_range}; 인원: {brief.travelers or '미정'}"
