from __future__ import annotations

from travel_agent.app.llm.direct_answer import (
    CodexOAuthAnswerClient,
    DirectLLMAnswerClient,
)


def test_codex_oauth_answer_client_extracts_agent_message() -> None:
    stdout = "\n".join(
        [
            '{"type":"thread.started","thread_id":"test"}',
            '{"type":"item.completed","item":{"type":"agent_message","text":"바로 답변입니다."}}',
            "2026-06-04T00:00:00Z WARN ignored stderr-like line",
        ]
    )

    client = CodexOAuthAnswerClient()

    assert client._extract_answer_from_jsonl(stdout) == "바로 답변입니다."


def test_codex_oauth_answer_client_enables_web_search_by_default() -> None:
    client = CodexOAuthAnswerClient(command="codex")

    command = client._build_command("C:\\temp")

    assert "--search" in command
    assert command.index("--search") < command.index("exec")


def test_codex_oauth_answer_client_subprocess_env_excludes_secrets(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "secret-openai")
    monkeypatch.setenv("SKYSCANNER_API_KEY", "secret-skyscanner")
    monkeypatch.setenv("PATH", "test-path")
    client = CodexOAuthAnswerClient(command="codex")

    env = client._subprocess_env()

    assert env["PATH"] == "test-path"
    assert "OPENAI_API_KEY" not in env
    assert "SKYSCANNER_API_KEY" not in env


def test_direct_llm_answer_client_enables_web_search_by_default() -> None:
    client = DirectLLMAnswerClient(api_key="test-key", model="test-model")

    payload = client._build_payload(
        message="삿포로 항공권 찾아줘",
        locale="ko-KR",
        currency="KRW",
        timezone="Asia/Seoul",
    )

    assert payload["tools"] == [{"type": "web_search_preview"}]
