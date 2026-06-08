from __future__ import annotations

from fastapi.testclient import TestClient

from travel_agent.app.llm.direct_answer import (
    CodexOAuthAnswerClient,
    DirectLLMAnswerClient,
)
from travel_agent.app.main import create_app
from travel_agent.app.schemas.llm import (
    DomainAgentRun,
    FlightSearchAnswerContext,
    FlightSourceAttempt,
)

BASE_LLM_PAYLOAD = {
    "locale": "ko-KR",
    "currency": "KRW",
    "timezone": "Asia/Seoul",
}


def test_llm_answer_endpoint_uses_codex_oauth_without_openai_key(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_answer(self, **kwargs) -> str:
        captured["client"] = type(self).__name__
        captured.update(kwargs)
        return "Codex OAuth로 바로 답변했습니다."

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ENABLE_FLIGHT_SOURCE_PROBES", "false")
    monkeypatch.setattr(CodexOAuthAnswerClient, "answer", fake_answer)
    client = TestClient(create_app("sqlite:///:memory:"))

    response = client.post(
        "/llm/answer",
        json={**BASE_LLM_PAYLOAD, "message": "삿포로 항공권 찾아줘"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "Codex OAuth로 바로 답변했습니다.",
        "answer_kind": "answer",
        "interpreted_request": None,
        "source_attempts": [],
        "blockers": [],
        "agent_runs": [],
    }
    assert captured["client"] == "CodexOAuthAnswerClient"
    assert captured["message"] == "삿포로 항공권 찾아줘"
    assert captured["locale"] == "ko-KR"


def test_llm_answer_endpoint_sends_raw_message_to_llm(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_answer(self, **kwargs) -> str:
        captured.update(kwargs)
        return "LLM이 바로 답변했습니다."

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ENABLE_FLIGHT_SOURCE_PROBES", "false")
    monkeypatch.setattr(DirectLLMAnswerClient, "answer", fake_answer)
    client = TestClient(create_app("sqlite:///:memory:"))

    response = client.post(
        "/llm/answer",
        json={**BASE_LLM_PAYLOAD, "message": "삿포로 여행갈건데 항공권 찾아줘"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "LLM이 바로 답변했습니다.",
        "answer_kind": "answer",
        "interpreted_request": None,
        "source_attempts": [],
        "blockers": [],
        "agent_runs": [],
    }
    assert captured["message"] == "삿포로 여행갈건데 항공권 찾아줘"
    assert captured["locale"] == "ko-KR"


def test_llm_answer_endpoint_passes_candidate_context_to_llm(monkeypatch) -> None:
    captured: dict[str, str] = {}
    context = FlightSearchAnswerContext(
        interpreted_request="항공 검색: 서울 -> Sapporo, 2026-07-03 ~ 2026-07-15",
        source_attempts=[
            FlightSourceAttempt(
                provider="naver_flight",
                title="네이버 항공권",
                source_url="https://flight.naver.com/test",
                status="candidate_found",
                summary="직항 후보 2개를 확인했습니다.",
                evidence=["fare_option=KE765", "fare_option=LJ301"],
                fare_options_found=True,
            )
        ],
        agent_runs=[
            DomainAgentRun(
                agent_name="FlightSearchAnswerAgent",
                title="항공권 검색 agent",
                status="completed",
                summary="항공권 검색 출처를 확인했습니다.",
            )
        ],
    )

    def fake_context(self, **kwargs) -> FlightSearchAnswerContext:
        captured["context_message"] = kwargs["message"]
        return context

    def fake_answer(self, **kwargs) -> str:
        captured["llm_message"] = kwargs["message"]
        return "확인된 후보를 기준으로 답변했습니다."

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "travel_agent.app.api.routes_llm.CoreTravelAnswerOrchestrator.build_context",
        fake_context,
    )
    monkeypatch.setattr(DirectLLMAnswerClient, "answer", fake_answer)
    client = TestClient(create_app("sqlite:///:memory:"))

    response = client.post(
        "/llm/answer",
        json={**BASE_LLM_PAYLOAD, "message": "삿포로 항공권 찾아줘"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "확인된 후보를 기준으로 답변했습니다."
    assert data["interpreted_request"] == context.interpreted_request
    assert data["source_attempts"][0]["provider"] == "naver_flight"
    assert data["agent_runs"][0]["agent_name"] == "FlightSearchAnswerAgent"
    assert "core orchestrator가 실행한 하위 agent 결과" in captured["llm_message"]
    assert "네이버 항공권" in captured["llm_message"]


def test_llm_answer_endpoint_blocks_link_only_flight_answers(monkeypatch) -> None:
    context = FlightSearchAnswerContext(
        interpreted_request="항공 검색: 서울 -> Sapporo, 2026-07-03 ~ 2026-07-15",
        source_attempts=[
            FlightSourceAttempt(
                provider="skyscanner",
                title="스카이스캐너",
                source_url="https://www.skyscanner.co.kr/transport/flights/sel/cts/260703/",
                status="requires_browser_network",
                summary="검색 페이지 접근만 확인했고 실시간 운임 후보는 추출하지 못했습니다.",
                evidence=["verdict=page_available"],
                fare_options_found=False,
            ),
            FlightSourceAttempt(
                provider="naver_flight",
                title="네이버 항공권",
                source_url="https://flight.naver.com/test",
                status="failed",
                summary="공개 검색 URL이 HTTP 503으로 응답했습니다.",
                evidence=["http_status=503"],
                fare_options_found=False,
            ),
        ],
        blockers=["실시간 항공권 후보를 자동 확정하지 못했습니다."],
        agent_runs=[
            DomainAgentRun(
                agent_name="FlightSearchAnswerAgent",
                title="항공권 검색 agent",
                status="completed",
                summary="항공권 검색 출처를 확인했습니다.",
            )
        ],
    )

    def fake_context(self, **kwargs) -> FlightSearchAnswerContext:
        return context

    def fake_answer(self, **kwargs) -> str:
        raise AssertionError("link-only flight context must not be sent to LLM")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "travel_agent.app.api.routes_llm.CoreTravelAnswerOrchestrator.build_context",
        fake_context,
    )
    monkeypatch.setattr(DirectLLMAnswerClient, "answer", fake_answer)
    client = TestClient(create_app("sqlite:///:memory:"))

    response = client.post(
        "/llm/answer",
        json={**BASE_LLM_PAYLOAD, "message": "삿포로 항공권 찾아줘"},
    )

    assert response.status_code == 200
    answer = response.json()["answer"]
    assert response.json()["answer_kind"] == "blocked"
    assert "항공권 후보를 아직 찾지 못했습니다." in answer
    assert "스카이스캐너: 검색 페이지 접근만 확인" in answer
    assert "네이버 항공권: 공개 검색 URL이 HTTP 503" in answer
    assert "날짜를 바꿔보" not in answer
    assert "가장 빠릅니다" not in answer


def test_llm_answer_endpoint_hides_internal_errors(monkeypatch) -> None:
    def fake_answer(self, **kwargs) -> str:
        raise RuntimeError("secret internal path")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ENABLE_FLIGHT_SOURCE_PROBES", "false")
    monkeypatch.setattr(DirectLLMAnswerClient, "answer", fake_answer)
    client = TestClient(create_app("sqlite:///:memory:"))

    response = client.post(
        "/llm/answer",
        json={**BASE_LLM_PAYLOAD, "message": "삿포로 항공권 찾아줘"},
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail == "LLM 응답 생성에 실패했습니다. 잠시 후 다시 시도해 주세요."
    assert "secret" not in detail
