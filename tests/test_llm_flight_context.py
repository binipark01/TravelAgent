from __future__ import annotations

from travel_agent.app.config import Settings
from travel_agent.app.llm.flight_search_context import build_flight_search_answer_context
from travel_agent.app.llm.flight_source_probe import (
    FlightSourceProbeResult,
    FlightSourceProbeRunner,
    safe_flight_redirect_url,
    safe_flight_source_url,
)
from travel_agent.app.llm.travel_answer_orchestrator import (
    CoreTravelAnswerOrchestrator,
    travel_answer_prompt,
)
from travel_agent.app.schemas.llm import FlightFareCandidate


class FakeFlightSourceProbeRunner(FlightSourceProbeRunner):
    def probe(self, source: str, url: str) -> FlightSourceProbeResult:
        return FlightSourceProbeResult(
            source=source,
            ok=source != "google_flights",
            verdict="weak_ok" if source != "google_flights" else "challenge",
            summary=f"{source} probe",
            status_code=200,
            body_size=68_575,
            reasons=["marker:captcha"] if source == "google_flights" else [],
            error=None,
            final_url=url,
        )


class PartiallyFailingFlightSourceProbeRunner(FlightSourceProbeRunner):
    def probe(self, source: str, url: str) -> FlightSourceProbeResult:
        if source == "skyscanner":
            raise RuntimeError("probe failure")
        return FlightSourceProbeResult(
            source=source,
            ok=True,
            verdict="page_available",
            summary=f"{source} probe",
            status_code=200,
            final_url=url,
        )


class RecordingFlightSourceProbeRunner(FlightSourceProbeRunner):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def probe(self, source: str, url: str) -> FlightSourceProbeResult:
        self.calls.append(source)
        return FlightSourceProbeResult(
            source=source,
            ok=True,
            verdict="page_available",
            summary=f"{source} probe",
            status_code=200,
            final_url=url,
        )


class CandidateFlightSourceProbeRunner(FlightSourceProbeRunner):
    def probe(self, source: str, url: str) -> FlightSourceProbeResult:
        if source != "naver_flight":
            return FlightSourceProbeResult(
                source=source,
                ok=False,
                verdict="not_run",
                summary=f"{source} skipped",
                final_url=url,
            )
        return FlightSourceProbeResult(
            source=source,
            ok=True,
            verdict="fare_options_found",
            summary="Naver 항공권 화면에서 후보를 추출했습니다.",
            status_code=200,
            final_url=url,
            fare_options=[
                FlightFareCandidate(
                    provider="naver_flight",
                    airline="진에어",
                    outbound_departure="08:20 ICN",
                    outbound_arrival="11:00 CTS",
                    inbound_departure="12:10 CTS",
                    inbound_arrival="15:05 ICN",
                    outbound_duration="직항, 02시간 40분",
                    inbound_duration="직항, 02시간 55분",
                    price="왕복 569,900원~",
                    stops="직항",
                    source_url=url,
                )
            ],
        )


def test_flight_search_context_builds_source_attempts_without_fake_fares() -> None:
    context = build_flight_search_answer_context(
        message=(
            "삿포로 여행갈건데 기간은 7월 초 중순 사이고 오전출발 비행기 "
            "돌아오는건 오후출발 비행기 항공권 찾아줘"
        ),
        currency="KRW",
        enable_live_probes=True,
        probe_runner=FakeFlightSourceProbeRunner(),
        reference_year=2026,
    )

    assert context.interpreted_request is not None
    assert "서울 -> Sapporo" in context.interpreted_request
    assert "2026-07-03 ~ 2026-07-15" in context.interpreted_request
    assert [attempt.provider for attempt in context.source_attempts] == [
        "naver_flight",
        "skyscanner",
        "google_flights",
    ]
    assert all(attempt.fare_options_found is False for attempt in context.source_attempts)
    assert any("실시간 항공권 후보를 자동 확정하지 못했습니다" in item for item in context.blockers)


def test_flight_search_context_uses_extracted_fare_candidates() -> None:
    context = build_flight_search_answer_context(
        message="삿포로 항공편 찾아줘 7월 초 중순 오전 출발 오후 귀국",
        currency="KRW",
        enable_live_probes=True,
        probe_runner=CandidateFlightSourceProbeRunner(),
        reference_year=2026,
    )

    naver = next(
        attempt for attempt in context.source_attempts if attempt.provider == "naver_flight"
    )
    prompt = travel_answer_prompt("삿포로 항공권 찾아줘", context)

    assert context.blockers == []
    assert naver.status == "candidate_found"
    assert naver.fare_options_found is True
    assert naver.fare_options[0].price == "왕복 569,900원~"
    assert "진에어" in prompt
    assert "왕복 569,900원~" in prompt


def test_flight_search_context_accepts_biyeonggi_keyword_and_isolates_probe_failures() -> None:
    context = build_flight_search_answer_context(
        message="삿포로 비행기 찾아줘 7월 초 중순 오전 출발 오후 귀국",
        currency="KRW",
        enable_live_probes=True,
        probe_runner=PartiallyFailingFlightSourceProbeRunner(),
        reference_year=2026,
    )

    assert context.interpreted_request is not None
    assert [attempt.provider for attempt in context.source_attempts] == [
        "naver_flight",
        "skyscanner",
        "google_flights",
    ]
    skyscanner = next(
        attempt for attempt in context.source_attempts if attempt.provider == "skyscanner"
    )
    assert skyscanner.status == "failed"
    assert "runner_error" in skyscanner.evidence[0]


def test_flight_search_context_checks_google_naver_and_skyscanner_sources() -> None:
    runner = RecordingFlightSourceProbeRunner()
    context = build_flight_search_answer_context(
        message="삿포로 항공편 찾아줘 7월 초 중순 오전 출발 오후 귀국",
        currency="KRW",
        enable_live_probes=True,
        probe_runner=runner,
        reference_year=2026,
    )

    assert runner.calls == ["naver_flight", "skyscanner", "google_flights"]
    statuses = {attempt.provider: attempt.status for attempt in context.source_attempts}
    assert statuses["naver_flight"] == "requires_browser_network"
    assert statuses["skyscanner"] == "requires_browser_network"
    assert statuses["google_flights"] == "requires_browser_network"


def test_core_travel_answer_orchestrator_runs_flight_and_accommodation_agents() -> None:
    runner = RecordingFlightSourceProbeRunner()
    orchestrator = CoreTravelAnswerOrchestrator(
        Settings(
            enable_flight_source_probes=True,
            enable_live_providers=False,
            provider_fallback_to_mock=True,
        ),
        flight_probe_runner=runner,
    )

    context = orchestrator.build_context(
        message=(
            "오사카 2026-10-03부터 2026-10-07까지 성인 2명 "
            "오전 출발 항공권이랑 교통 좋은 호텔 찾아줘"
        ),
        locale="ko-KR",
        currency="KRW",
        timezone="Asia/Seoul",
    )

    agent_names = [agent_run.agent_name for agent_run in context.agent_runs]
    assert agent_names == [
        "IntakeAgent",
        "FlightSearchAnswerAgent",
        "AccommodationAgent",
    ]
    assert runner.calls == ["naver_flight", "skyscanner", "google_flights"]
    assert any(attempt.domain == "flights" for attempt in context.source_attempts)
    assert any(attempt.domain == "accommodations" for attempt in context.source_attempts)
    accommodation = next(
        attempt for attempt in context.source_attempts if attempt.domain == "accommodations"
    )
    assert accommodation.provider == "mock_accommodation"
    assert accommodation.status == "simulated_result"
    assert accommodation.options_found is True
    assert context.interpreted_request is not None
    assert "항공 검색" in context.interpreted_request
    assert "숙소 검색" in context.interpreted_request


def test_safe_flight_source_url_matches_known_source_urls() -> None:
    assert (
        safe_flight_source_url(
            source="naver_flight",
            url="https://flight.naver.com/flights/international/ICN-CTS-test",
        )
        is not None
    )
    assert safe_flight_source_url(source="naver_flight", url="javascript:alert(1)") is None
    assert safe_flight_source_url(source="naver_flight", url="https://example.com/test") is None
    assert (
        safe_flight_source_url(source="google_flights", url="https://www.google.com/sorry/")
        is None
    )
    assert (
        safe_flight_redirect_url(
            source="google_flights",
            current_url="https://www.google.com/travel/flights?q=test",
            redirect_url="http://127.0.0.1/internal",
        )
        is None
    )
    assert (
        safe_flight_redirect_url(
            source="google_flights",
            current_url="https://www.google.com/travel/flights?q=test",
            redirect_url="/travel/flights/booking",
        )
        is not None
    )
