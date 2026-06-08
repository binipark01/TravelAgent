from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from travel_agent.app.agents.intake import IntakeAgent
from travel_agent.app.llm.flight_search_links import FlightSearchLinks, build_flight_search_links
from travel_agent.app.llm.flight_source_probe import (
    FlightSourceProbeResult,
    FlightSourceProbeRunner,
    safe_flight_source_url,
)
from travel_agent.app.schemas.llm import (
    DomainAgentRun,
    FlightSearchAnswerContext,
    FlightSourceAttempt,
)


def build_flight_search_answer_context(
    *,
    message: str,
    currency: str,
    enable_live_probes: bool,
    probe_runner: FlightSourceProbeRunner,
    reference_year: int | None = None,
) -> FlightSearchAnswerContext:
    if not enable_live_probes:
        return FlightSearchAnswerContext()
    intake = IntakeAgent().run(message, currency=currency, reference_year=reference_year)
    preference = intake.brief.transport_preference or ""
    if "flight_search" not in preference:
        return FlightSearchAnswerContext()
    links = build_flight_search_links(intake.brief)
    if not links:
        return FlightSearchAnswerContext(
            blockers=[
                "항공 검색에 필요한 출발지, 목적지, 날짜 또는 공항 코드를 "
                "확정하지 못했습니다."
            ]
        )
    source_attempts = _source_attempts(
        links=links,
        enable_live_probes=enable_live_probes,
        probe_runner=probe_runner,
    )
    has_fare_options = any(attempt.fare_options_found for attempt in source_attempts)
    blockers = (
        []
        if has_fare_options
        else [
            "실시간 항공권 후보를 자동 확정하지 못했습니다. "
            "확인된 검색 조건과 출처 상태만 답변에 사용해야 합니다."
        ]
    )
    agent_summary = (
        "실시간 항공권 후보를 추출했습니다."
        if has_fare_options
        else "Google Flights, 네이버 항공권, 스카이스캐너 검색 출처를 확인했습니다."
    )
    return FlightSearchAnswerContext(
        interpreted_request=links.summary(),
        source_attempts=source_attempts,
        blockers=blockers,
        agent_runs=[
            DomainAgentRun(
                agent_name="FlightSearchAnswerAgent",
                title="항공권 검색 agent",
                status="completed",
                summary=agent_summary,
                evidence=[attempt.provider for attempt in source_attempts],
            )
        ],
    )


def context_prompt(message: str, context: FlightSearchAnswerContext) -> str:
    if not context.has_content():
        return message
    lines = [
        "사용자 원문:",
        message,
        "",
        "실제 검색 출처 확인 결과:",
    ]
    if context.interpreted_request:
        lines.append(f"- 해석된 요청: {context.interpreted_request}")
    if context.agent_runs:
        lines.append("- 실행한 하위 agent:")
        for agent_run in context.agent_runs:
            lines.append(
                f"  - {agent_run.title}: status={agent_run.status}; "
                f"summary={agent_run.summary}"
            )
    for attempt in context.source_attempts:
        lines.append(
            f"- {attempt.title}: status={attempt.status}; url={attempt.source_url}; "
            f"summary={attempt.summary}"
        )
        for evidence in attempt.evidence:
            lines.append(f"  - evidence: {evidence}")
        for option in attempt.fare_options:
            inbound = (
                f"{option.inbound_departure or '없음'}"
                f"->{option.inbound_arrival or '없음'}"
            )
            lines.append(
                f"  - fare_option: {option.airline}; "
                f"outbound={option.outbound_departure}->{option.outbound_arrival}; "
                f"inbound={inbound}; "
                f"price={option.price}; stops={option.stops or '미확인'}"
            )
    if context.blockers:
        lines.append("")
        lines.append("blocker:")
        lines.extend(f"- {blocker}" for blocker in context.blockers)
    lines.extend(
        [
            "",
            "답변 규칙:",
            "- 실제 운임, 좌석 수, 항공편 번호를 출처 근거 없이 만들지 말 것.",
            "- 자동 조회가 막힌 검색 출처는 제한 사항으로 명확히 말할 것.",
            "- 운임 후보가 없으면 추천이라고 단정하지 말고 조회 조건과 확인 필터만 말할 것.",
            "- 사용자가 바로 확인할 수 있도록 출처 URL과 검색 조건을 제시할 것.",
        ]
    )
    return "\n".join(lines)


def _source_attempts(
    *,
    links: FlightSearchLinks,
    enable_live_probes: bool,
    probe_runner: FlightSourceProbeRunner,
) -> list[FlightSourceAttempt]:
    sources = [
        ("naver_flight", "네이버 항공권", links.naver_url),
        ("skyscanner", "스카이스캐너", links.skyscanner_url),
        ("google_flights", "Google Flights", links.google_url),
    ]
    attempts: list[FlightSourceAttempt] = []
    if not enable_live_probes:
        for source, title, url in sources:
            attempts.append(
                _attempt_from_probe(
                    title=title,
                    url=url,
                    probe=FlightSourceProbeResult(
                        source=source,
                        ok=False,
                        verdict="not_run",
                        summary="live source probe가 설정에서 꺼져 있습니다.",
                        final_url=url,
                    ),
                )
            )
        return attempts

    ordered_attempts: list[FlightSourceAttempt | None] = [None for _ in sources]
    with ThreadPoolExecutor(max_workers=len(sources)) as executor:
        futures = {
            executor.submit(probe_runner.probe, source, url): (index, source, title, url)
            for index, (source, title, url) in enumerate(sources)
        }
        for future in as_completed(futures):
            index, source, title, url = futures[future]
            try:
                probe = future.result()
            except (OSError, RuntimeError, ValueError) as exc:
                probe = FlightSourceProbeResult(
                    source=source,
                    ok=False,
                    verdict="runner_error",
                    summary="source probe 실행에 실패했습니다.",
                    error=str(exc),
                    final_url=url,
                )
            ordered_attempts[index] = _attempt_from_probe(
                title=title,
                url=url,
                probe=probe,
            )
    return [attempt for attempt in ordered_attempts if attempt is not None]


def _attempt_from_probe(
    *, title: str, url: str, probe: FlightSourceProbeResult
) -> FlightSourceAttempt:
    status = _status_for_probe(probe)
    evidence = [
        f"verdict={probe.verdict}",
        f"summary={probe.summary}",
    ]
    if probe.status_code:
        evidence.append(f"http_status={probe.status_code}")
    if probe.body_size:
        evidence.append(f"body_size={probe.body_size}")
    evidence.extend(f"reason={reason}" for reason in probe.reasons)
    source_url = safe_flight_source_url(source=probe.source, url=probe.final_url or url) or url
    return FlightSourceAttempt(
        domain="flights",
        agent_name="FlightSearchAnswerAgent",
        provider=probe.source,
        title=title,
        source_url=source_url,
        status=status,
        summary=_summary_for_probe(probe),
        evidence=evidence,
        options_found=bool(probe.fare_options),
        fare_options_found=bool(probe.fare_options),
        fare_options=probe.fare_options,
    )


def _status_for_probe(probe: FlightSourceProbeResult) -> str:
    if probe.fare_options:
        return "candidate_found"
    if probe.verdict in {"not_run", "not_configured"}:
        return probe.verdict
    if probe.verdict == "challenge":
        return "restricted"
    if probe.ok:
        return "requires_browser_network"
    return "failed"


def _summary_for_probe(probe: FlightSourceProbeResult) -> str:
    if probe.source == "naver_flight" and probe.fare_options:
        return f"실제 화면에서 항공권 후보 {len(probe.fare_options)}개를 확인했습니다."
    if probe.source == "naver_flight" and probe.ok:
        return (
            "공개 검색 URL 응답은 확인했지만 실시간 운임은 사이트 화면에서 확인해야 합니다."
        )
    if probe.source == "skyscanner" and probe.ok:
        return "공개 검색 URL 응답은 확인했지만 실시간 가격은 사이트 화면에서 표시됩니다."
    if probe.source == "google_flights" and probe.verdict == "challenge":
        return "Google Flights는 자동 접근 제한 화면으로 응답했습니다."
    return probe.summary
