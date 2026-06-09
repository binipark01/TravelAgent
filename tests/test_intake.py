from __future__ import annotations

from travel_agent.app.agents.intake import IntakeAgent
from travel_agent.app.orchestration.state_machine import critical_missing_fields
from travel_agent.app.schemas.brief import TripBrief
from travel_agent.app.schemas.trip import TripPlanState


class _RecordingLLM:
    """extract_trip_brief가 받은 history를 기록하는 가짜 LLM 클라이언트."""

    def __init__(self) -> None:
        self.seen_history: list[str] | None = None

    def extract_trip_brief(
        self, message: str, currency: str, history: list[str] | None = None
    ) -> TripBrief:
        self.seen_history = history
        return TripBrief(currency=currency, destinations=["Sapporo"])


def test_intake_passes_history_to_llm() -> None:
    client = _RecordingLLM()
    agent = IntakeAgent(llm_client=client, enable_live_llm=True)

    agent.run("거기 숙소도 찾아줘", currency="KRW", history=["삿포로 항공권 찾아줘"])

    assert client.seen_history == ["삿포로 항공권 찾아줘"]


def test_trip_brief_extraction_fallback() -> None:
    result = IntakeAgent().run(
        "10월 초에 여자친구랑 4박 5일 일본 가고 싶어. 예산은 1인 120만원 정도. 맛집이랑 쇼핑 위주.",
        reference_year=2026,
    )

    assert result.brief.destinations == ["Japan"]
    assert result.brief.travelers == 2
    assert result.brief.duration_days == 5
    assert result.brief.budget_per_person == 1_200_000
    assert result.brief.budget_total == 2_400_000
    assert "food" in result.brief.must_include
    assert "shopping" in result.brief.must_include
    assert set(result.brief.missing_fields) == {"origin", "passport_country"}


def test_missing_fields_detection() -> None:
    state = TripPlanState(trip_id="trip_test", raw_user_message="일본 여행")
    state.brief = IntakeAgent().run("일본 여행", reference_year=2026).brief

    assert critical_missing_fields(state) == []

    empty_state = TripPlanState(trip_id="trip_empty", raw_user_message="그냥 여행")
    empty_state.brief = IntakeAgent().run("그냥 여행", reference_year=2026).brief

    # 후속 질문이 비활성화되어 필수 누락으로 인한 차단은 발생하지 않는다.
    assert critical_missing_fields(empty_state) == []


def test_sapporo_flight_search_intake_defaults() -> None:
    message = (
        "삿포로 여행갈건데 기간은 7월 초 중순 사이고 "
        "오전출발 비행기 돌아오는건 오후출발 비행기 항공권 찾아줘"
    )
    result = IntakeAgent().run(
        message,
        reference_year=2026,
    )

    brief = result.brief
    assert brief.destinations == ["Sapporo"]
    assert brief.origin == "서울"
    assert brief.travelers == 1
    assert brief.start_date and brief.start_date.isoformat() == "2026-07-03"
    assert brief.end_date and brief.end_date.isoformat() == "2026-07-15"
    assert brief.transport_preference == "flight, flight_search, outbound_morning, return_afternoon"
    assert brief.missing_fields == []


def test_flexible_window_keeps_range_and_duration() -> None:
    result = IntakeAgent().run(
        "삿포로 여행갈건데 7월 초에서 중순사이에 갈거거던? 4박5일정도로 항공권 찾아줘",
        reference_year=2026,
    )

    brief = result.brief
    assert brief.destinations == ["Sapporo"]
    assert brief.duration_days == 5
    assert brief.duration_nights == 4
    assert brief.start_date is not None
    assert brief.end_date is not None
    # 유연 날짜: 범위(window)가 여행 길이보다 넓게 유지된다(여러 출발일 검색용).
    assert (brief.end_date - brief.start_date).days > brief.duration_nights


def test_fallback_parser_uses_history_to_keep_context() -> None:
    # 브라우저 멀티턴: 매 턴이 새 run이라 existing_brief가 없어도, 규칙 파서가
    # history를 누적해 이전 목적지를 기억해야 한다(LLM 실패 시 안전망).
    agent = IntakeAgent(enable_live_llm=False)

    result = agent.run("4박5일로 가고싶어", history=["삿포로 가고싶어"])
    brief = result.brief
    assert "Sapporo" in brief.destinations  # 목적지를 잊지 않는다
    assert brief.duration_days == 5

    # 추가 정보(인원)도 누적된다
    result2 = agent.run(
        "2명이서 갈거야", history=["삿포로 가고싶어", "4박5일로 가고싶어"]
    )
    brief2 = result2.brief
    assert "Sapporo" in brief2.destinations
    assert brief2.duration_days == 5
    assert brief2.travelers == 2


def test_fallback_parser_without_history_unchanged() -> None:
    # history가 없으면 기존 단일 메시지 파싱과 동일해야 한다(회귀 방지).
    agent = IntakeAgent(enable_live_llm=False)
    result = agent.run("삿포로 4박5일 여행", history=None)
    assert result.brief.destinations == ["Sapporo"]
    assert result.brief.duration_days == 5


class _FlakyLLM:
    """앞선 N번은 일시적 실패, 그 다음엔 성공하는 가짜 클라이언트."""

    def __init__(self, fail_times: int, error: Exception) -> None:
        self.fail_times = fail_times
        self.error = error
        self.calls = 0

    def extract_trip_brief(self, message, currency, history=None):
        from travel_agent.app.schemas.brief import TripBrief

        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.error
        return TripBrief(currency=currency, destinations=["Sapporo"])


def test_llm_retries_transient_failure_and_stays_authoritative() -> None:
    from travel_agent.app.agents.llm_client import RetryableBriefError

    client = _FlakyLLM(fail_times=1, error=RetryableBriefError("빈 출력"))
    agent = IntakeAgent(llm_client=client, enable_live_llm=True, llm_max_attempts=2)

    result = agent.run("삿포로 가고싶어")

    # 1차 일시 실패 → 2차 성공: 파서 폴백이 아니라 LLM 결과를 쓴다.
    assert client.calls == 2
    assert result.brief.destinations == ["Sapporo"]


def test_llm_timeout_falls_back_immediately_without_retry() -> None:
    # 타임아웃류(비싼 실패)는 재시도하지 않고 즉시 폴백(지연 폭증 방지).
    client = _FlakyLLM(fail_times=99, error=TimeoutError("느림"))
    agent = IntakeAgent(llm_client=client, enable_live_llm=True, llm_max_attempts=3)

    result = agent.run("삿포로 4박5일", history=["삿포로 가고싶어"])

    assert client.calls == 1  # 재시도 없음
    # 폴백이지만 history 덕분에 목적지는 유지된다.
    assert "Sapporo" in result.brief.destinations


def test_llm_all_retries_fail_falls_back_with_history() -> None:
    from travel_agent.app.agents.llm_client import RetryableBriefError

    client = _FlakyLLM(fail_times=99, error=RetryableBriefError("계속 깨짐"))
    agent = IntakeAgent(llm_client=client, enable_live_llm=True, llm_max_attempts=2)

    result = agent.run("4박5일로", history=["삿포로 가고싶어"])

    assert client.calls == 2  # 시도 횟수만큼만
    assert "Sapporo" in result.brief.destinations  # 폴백도 history 누적
