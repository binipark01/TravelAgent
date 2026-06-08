from __future__ import annotations

from typing import Literal

from pydantic import Field

from travel_agent.app.schemas.common import StrictBaseModel


class LLMAnswerRequest(StrictBaseModel):
    message: str
    locale: str = "ko-KR"
    currency: str = "KRW"
    timezone: str = "Asia/Seoul"


class FlightFareCandidate(StrictBaseModel):
    provider: str
    airline: str
    outbound_departure: str
    outbound_arrival: str
    inbound_departure: str | None = None
    inbound_arrival: str | None = None
    outbound_duration: str | None = None
    inbound_duration: str | None = None
    price: str
    stops: str | None = None
    source_url: str | None = None
    notes: list[str] = Field(default_factory=list)


class FlightSourceAttempt(StrictBaseModel):
    domain: str = "flights"
    agent_name: str = "FlightSearchAnswerAgent"
    provider: str
    title: str
    source_url: str | None = None
    status: str
    summary: str
    evidence: list[str] = Field(default_factory=list)
    options_found: bool = False
    fare_options_found: bool = False
    fare_options: list[FlightFareCandidate] = Field(default_factory=list)


class DomainAgentRun(StrictBaseModel):
    agent_name: str
    title: str
    status: str
    summary: str
    evidence: list[str] = Field(default_factory=list)


class FlightSearchAnswerContext(StrictBaseModel):
    interpreted_request: str | None = None
    source_attempts: list[FlightSourceAttempt] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    agent_runs: list[DomainAgentRun] = Field(default_factory=list)

    def has_content(self) -> bool:
        return bool(
            self.interpreted_request
            or self.source_attempts
            or self.blockers
            or self.agent_runs
        )


class LLMAnswerResponse(StrictBaseModel):
    answer: str
    answer_kind: Literal["answer", "blocked"] = "answer"
    interpreted_request: str | None = None
    source_attempts: list[FlightSourceAttempt] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    agent_runs: list[DomainAgentRun] = Field(default_factory=list)
