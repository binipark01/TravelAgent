from __future__ import annotations

from travel_agent.app.llm.travel_answer_orchestrator import travel_answer_prompt
from travel_agent.app.schemas.llm import (
    DomainAgentRun,
    FlightFareCandidate,
    FlightSearchAnswerContext,
    FlightSourceAttempt,
)


def test_travel_answer_prompt_includes_agent_results() -> None:
    context = FlightSearchAnswerContext(
        agent_runs=[
            DomainAgentRun(
                agent_name="AccommodationAgent",
                title="숙소 검색 agent",
                status="completed",
                summary="1개 숙소 후보를 확인했습니다.",
            )
        ],
        source_attempts=[
            FlightSourceAttempt(
                domain="accommodations",
                agent_name="AccommodationAgent",
                provider="mock_accommodation",
                title="Osaka Mock Central Hotel",
                status="simulated_result",
                summary="총 600,000 KRW",
                options_found=True,
            )
        ],
    )

    prompt = travel_answer_prompt("오사카 호텔 찾아줘", context)

    assert "숙소 검색 agent" in prompt
    assert (
        "검색 출처 및 후보 목록에 없는 항공편, 호텔명, 가격, URL을 새로 추가하지 않는다"
        in prompt
    )
    assert "mock 또는 시뮬레이션 결과는 실제 예약 가능한 상품처럼 말하지 않는다" in prompt


def test_travel_answer_prompt_includes_flight_fare_candidates() -> None:
    context = FlightSearchAnswerContext(
        source_attempts=[
            FlightSourceAttempt(
                provider="naver_flight",
                title="네이버 항공권",
                status="candidate_found",
                summary="실제 화면에서 항공권 후보 1개를 확인했습니다.",
                fare_options_found=True,
                fare_options=[
                    FlightFareCandidate(
                        provider="naver_flight",
                        airline="진에어",
                        outbound_departure="08:20 ICN",
                        outbound_arrival="11:00 CTS",
                        inbound_departure="12:10 CTS",
                        inbound_arrival="15:05 ICN",
                        price="왕복 569,900원~",
                        stops="직항",
                    )
                ],
            )
        ]
    )

    prompt = travel_answer_prompt("삿포로 항공권 찾아줘", context)

    assert "진에어" in prompt
    assert "08:20 ICN->11:00 CTS" in prompt
    assert "왕복 569,900원~" in prompt
