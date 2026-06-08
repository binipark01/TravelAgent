from __future__ import annotations

from fastapi import APIRouter, HTTPException

from travel_agent.app.config import get_settings
from travel_agent.app.llm.direct_answer import CodexOAuthAnswerClient, DirectLLMAnswerClient
from travel_agent.app.llm.travel_answer_orchestrator import (
    CoreTravelAnswerOrchestrator,
    link_only_flight_blocked_answer,
    travel_answer_prompt,
)
from travel_agent.app.schemas.llm import LLMAnswerRequest, LLMAnswerResponse

router = APIRouter(prefix="/llm", tags=["llm"])


@router.post("/answer", response_model=LLMAnswerResponse)
def answer_with_llm(payload: LLMAnswerRequest) -> LLMAnswerResponse:
    settings = get_settings()
    search_context = CoreTravelAnswerOrchestrator(settings).build_context(
        message=payload.message,
        locale=payload.locale,
        currency=payload.currency,
        timezone=payload.timezone,
    )
    blocked_answer = link_only_flight_blocked_answer(search_context)
    if blocked_answer:
        return LLMAnswerResponse(
            answer=blocked_answer,
            answer_kind="blocked",
            interpreted_request=search_context.interpreted_request,
            source_attempts=search_context.source_attempts,
            blockers=search_context.blockers,
            agent_runs=search_context.agent_runs,
        )
    if settings.openai_api_key:
        client = DirectLLMAnswerClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            enable_web_search=settings.codex_oauth_enable_web_search,
        )
    else:
        client = CodexOAuthAnswerClient(
            command=settings.codex_cli_command,
            model=settings.codex_oauth_model,
            timeout_seconds=settings.codex_oauth_timeout_seconds,
            enable_web_search=settings.codex_oauth_enable_web_search,
        )
    try:
        answer = client.answer(
            message=travel_answer_prompt(payload.message, search_context),
            locale=payload.locale,
            currency=payload.currency,
            timezone=payload.timezone,
        )
    except (OSError, RuntimeError) as exc:
        raise HTTPException(
            status_code=502,
            detail="LLM 응답 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.",
        ) from exc
    return LLMAnswerResponse(
        answer=answer,
        interpreted_request=search_context.interpreted_request,
        source_attempts=search_context.source_attempts,
        blockers=search_context.blockers,
        agent_runs=search_context.agent_runs,
    )
