from __future__ import annotations

from dataclasses import dataclass

from travel_agent.app.agents.accommodation import AccommodationAgent
from travel_agent.app.schemas.brief import TripBrief
from travel_agent.app.schemas.llm import (
    DomainAgentRun,
    FlightSearchAnswerContext,
    FlightSourceAttempt,
)
from travel_agent.app.schemas.providers import AccommodationOption
from travel_agent.app.schemas.trip import TripPlanState
from travel_agent.app.tools.accommodation_search import AccommodationSearchTool
from travel_agent.app.utils.ids import new_id

ACCOMMODATION_KEYWORDS = (
    "숙소",
    "숙박",
    "호텔",
    "에어비앤비",
    "airbnb",
    "agoda",
    "booking.com",
)
FULL_PLAN_KEYWORDS = ("여행 계획", "일정", "코스", "동선")


@dataclass(frozen=True)
class AccommodationAnswerAgent:
    tool: AccommodationSearchTool

    def can_handle(self, message: str) -> bool:
        text = message.lower()
        return any(keyword in text for keyword in ACCOMMODATION_KEYWORDS) or any(
            keyword in text for keyword in FULL_PLAN_KEYWORDS
        )

    def run(
        self,
        *,
        message: str,
        state: TripPlanState,
    ) -> FlightSearchAnswerContext:
        if not self.can_handle(message):
            return FlightSearchAnswerContext()
        blockers = _missing_accommodation_inputs(state)
        if blockers:
            return FlightSearchAnswerContext(
                blockers=blockers,
                agent_runs=[
                    DomainAgentRun(
                        agent_name="AccommodationAgent",
                        title="숙소 검색 agent",
                        status="needs_user_input",
                        summary="숙소 후보 검색에 필요한 정보가 부족합니다.",
                        evidence=blockers,
                    )
                ],
            )
        agent = AccommodationAgent(self.tool)
        updated = agent.run(state)
        attempts = [_attempt_from_option(option) for option in updated.accommodation_options]
        summary = (
            f"{len(updated.accommodation_options)}개 숙소 후보를 확인했습니다."
            if updated.accommodation_options
            else "조건에 맞는 숙소 후보를 확인하지 못했습니다."
        )
        blockers = []
        if not updated.accommodation_options:
            blockers.append(
                "숙소 후보를 자동 확정하지 못했습니다. 목적지와 날짜를 다시 확인해야 합니다."
            )
        return FlightSearchAnswerContext(
            interpreted_request=_interpreted_request(updated),
            source_attempts=attempts,
            blockers=blockers,
            agent_runs=[
                DomainAgentRun(
                    agent_name="AccommodationAgent",
                    title="숙소 검색 agent",
                    status="completed" if updated.accommodation_options else "failed",
                    summary=summary,
                    evidence=[attempt.provider for attempt in attempts],
                )
            ],
        )


def build_accommodation_answer_context(
    *,
    message: str,
    state: TripPlanState,
    tool: AccommodationSearchTool,
) -> FlightSearchAnswerContext:
    return AccommodationAnswerAgent(tool).run(message=message, state=state)


def _missing_accommodation_inputs(state: TripPlanState) -> list[str]:
    brief = state.brief
    missing = []
    if not state.selected_destination:
        missing.append("숙소 검색에 필요한 목적지를 확정하지 못했습니다.")
    if not brief or not brief.start_date:
        missing.append("숙소 검색에 필요한 체크인 날짜를 확정하지 못했습니다.")
    if not brief or not brief.end_date:
        missing.append("숙소 검색에 필요한 체크아웃 날짜를 확정하지 못했습니다.")
    if not brief or not brief.travelers:
        missing.append("숙소 검색에 필요한 인원을 확정하지 못했습니다.")
    return missing


def _attempt_from_option(option: AccommodationOption) -> FlightSourceAttempt:
    source_ref = option.metadata.source_ref
    status = "simulated_result" if source_ref.is_mock else "candidate_found"
    return FlightSourceAttempt(
        domain="accommodations",
        agent_name="AccommodationAgent",
        provider=source_ref.provider,
        title=option.name,
        source_url=source_ref.source_url,
        status=status,
        summary=(
            f"1박 {option.nightly_price.amount:,.0f} {option.nightly_price.currency}, "
            f"총 {option.total_price.amount:,.0f} {option.total_price.currency}; "
            f"{option.cancellation_policy}"
        ),
        evidence=[
            f"provider={source_ref.provider}",
            f"source_type={source_ref.source_type}",
            f"is_mock={source_ref.is_mock}",
            f"confidence={source_ref.confidence}",
        ],
        options_found=True,
        fare_options_found=False,
    )


def _interpreted_request(state: TripPlanState) -> str | None:
    brief = state.brief
    if not brief or not state.selected_destination or not brief.start_date or not brief.end_date:
        return None
    return (
        f"숙소 검색: {state.selected_destination}, "
        f"{brief.start_date.isoformat()} ~ {brief.end_date.isoformat()}, "
        f"{brief.travelers or 1}명"
    )


def build_trip_plan_state_for_answer(
    *,
    message: str,
    locale: str,
    currency: str,
    timezone: str,
    brief: TripBrief,
) -> TripPlanState:
    selected_destination = brief.selected_destination or (
        brief.destinations[0] if brief.destinations else None
    )
    return TripPlanState(
        trip_id=new_id("llm_trip"),
        locale=locale,
        currency=currency,
        timezone=timezone,
        raw_user_message=message,
        raw_user_messages=[message],
        brief=brief,
        selected_destination=selected_destination,
    )
