from __future__ import annotations

from sqlalchemy.orm import Session

from travel_agent.app.agent_core.checkpoint import CheckpointStore
from travel_agent.app.agent_core.event_bus import EventBus
from travel_agent.app.agent_core.run_context import RunContext
from travel_agent.app.agents.supervisor import TravelSupervisorAgent as LegacyPlanningSupervisor
from travel_agent.app.config import Settings, get_settings
from travel_agent.app.db.repositories import AgentRunRepository, TripRepository
from travel_agent.app.evidence.store import EvidenceStore
from travel_agent.app.orchestration.agent_recorder import AgentRunRecorder
from travel_agent.app.orchestration.run_context import build_run_context
from travel_agent.app.orchestration.state_machine import add_audit_event
from travel_agent.app.providers.router import ProviderRouter
from travel_agent.app.schemas.agent import (
    AgentEvent,
    AgentEventType,
    AgentRun,
    AgentRunDetailResponse,
    AgentRunResponse,
    AgentRunStatus,
    AgentRunSummary,
    AgentStep,
    AgentStepStatus,
    TripStateSummary,
)
from travel_agent.app.schemas.common import TripStatus
from travel_agent.app.schemas.trip import TripPlanState
from travel_agent.app.sources.registry import SourceRegistry
from travel_agent.app.sources.source_discovery import SourceDiscoveryTool
from travel_agent.app.tools.travel_tools import ToolExecutor
from travel_agent.app.utils.ids import new_id
from travel_agent.app.utils.time import utc_now


class AgentRuntime:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.trip_repository = TripRepository(session)
        self.run_repository = AgentRunRepository(session)
        self.source_registry = SourceRegistry(self.settings)
        self.evidence_store = EvidenceStore(session)
        self.tool_executor = ToolExecutor(
            self.evidence_store, SourceDiscoveryTool(self.source_registry)
        )
        self.legacy_supervisor = LegacyPlanningSupervisor(build_run_context(self.settings))

    def start_run(
        self,
        message: str,
        *,
        user_id: str | None = None,
        locale: str = "ko-KR",
        currency: str = "KRW",
        timezone: str = "Asia/Seoul",
        history: list[str] | None = None,
    ) -> AgentRunResponse:
        # 과거 메시지 + 현재 메시지 순으로 보관해 intake가 대화 문맥을 참고하게 한다.
        prior = [m for m in (history or []) if m and m.strip()]
        state = TripPlanState(
            trip_id=new_id("trip"),
            user_id=user_id,
            locale=locale,
            currency=currency,
            timezone=timezone,
            raw_user_message=message,
            raw_user_messages=[*prior, message],
        )
        add_audit_event(state, "trip_created", "Agent run started.", actor="user")
        self.trip_repository.create_trip(state)
        run = AgentRun(
            run_id=new_id("run"),
            trip_id=state.trip_id,
            status=AgentRunStatus.queued,
            created_at=utc_now(),
            started_at=utc_now(),
        )
        self.run_repository.create_run(run)
        ctx = self._build_context(run.run_id, state)
        ctx.event_bus.emit(
            AgentEventType.user_message,
            "사용자가 여행 요청을 입력했습니다.",
            {"message": message},
        )
        self._execute(ctx, state)
        self.session.commit()
        persisted_run = self.run_repository.get_run(run.run_id)
        return AgentRunResponse(
            trip_id=state.trip_id,
            run_id=run.run_id,
            status=persisted_run.status,
            current_step=persisted_run.current_step,
            steps=self.run_repository.list_steps(run.run_id),
            missing_fields=state.missing_fields,
            questions=[self._question_for(field) for field in state.missing_fields],
            state_summary=self._state_summary(state),
            partial_plan=state,
            events=self.run_repository.list_events(run.run_id),
        )

    def continue_run(self, run_id: str, user_message: str | None = None) -> AgentRunDetailResponse:
        run = self.run_repository.get_run(run_id)
        state = self.trip_repository.load_latest_state(run.trip_id)
        if user_message:
            state.raw_user_message = f"{state.raw_user_message}\n{user_message}"
            state.raw_user_messages.append(user_message)
            add_audit_event(
                state,
                "message_added",
                "User supplied additional agent details.",
                actor="user",
            )
        ctx = self._build_context(run_id, state)
        if user_message:
            ctx.event_bus.emit(
                AgentEventType.user_message,
                "사용자가 추가 정보를 입력했습니다.",
                {"message": user_message},
            )
        self._execute(ctx, state, message=user_message)
        self.session.commit()
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> AgentRunDetailResponse:
        run = self.run_repository.get_run(run_id)
        state = self.trip_repository.load_latest_state(run.trip_id)
        return self._detail_response(run, state)

    def get_events(self, run_id: str) -> list[AgentEvent]:
        self.run_repository.get_run(run_id)
        return self.run_repository.list_events(run_id)

    def list_runs(self, limit: int = 30) -> list[AgentRunSummary]:
        summaries: list[AgentRunSummary] = []
        for run in self.run_repository.list_runs(limit):
            try:
                state = self.trip_repository.load_latest_state(run.trip_id)
            except Exception:  # noqa: BLE001 - 손상된 스냅샷은 목록에서 건너뛴다
                continue
            message = (state.raw_user_message or "").strip().replace("\n", " ")
            brief = state.brief
            date_range = None
            if brief and brief.start_date:
                date_range = brief.start_date.isoformat()
                if brief.end_date:
                    date_range = f"{date_range} ~ {brief.end_date.isoformat()}"
            summaries.append(
                AgentRunSummary(
                    run_id=run.run_id,
                    trip_id=run.trip_id,
                    status=run.status,
                    created_at=run.started_at,
                    message=message[:140],
                    destination=state.selected_destination,
                    date_range=date_range,
                )
            )
        return summaries

    def _build_context(self, run_id: str, state: TripPlanState) -> RunContext:
        event_bus = EventBus(self.run_repository, run_id=run_id, trip_id=state.trip_id)
        return RunContext(
            run_id=run_id,
            trip_id=state.trip_id,
            user_id=state.user_id,
            locale=state.locale,
            currency=state.currency,
            timezone=state.timezone,
            provider_router=ProviderRouter(self.settings),
            source_registry=self.source_registry,
            tool_executor=self.tool_executor,
            event_bus=event_bus,
            checkpoint_store=CheckpointStore(self.trip_repository),
            evidence_store=self.evidence_store,
            guardrail_executor=None,
            llm_client=None,
            dry_run=not self.settings.enable_live_providers,
            settings=self.settings,
        )

    def _execute(
        self,
        ctx: RunContext,
        state: TripPlanState,
        *,
        message: str | None = None,
    ) -> None:
        recorder = RuntimeRecorder(
            trip_id=state.trip_id,
            run_id=ctx.run_id,
            repository=self.run_repository,
        )
        try:
            self.run_repository.update_run(ctx.run_id, status=AgentRunStatus.running)
            self._record_source_discovery(ctx)
            self.legacy_supervisor.run_agent_workflow(state, message=message, recorder=recorder)
            packets = ctx.tool_executor.store_state_outputs(
                run_id=ctx.run_id,
                state=state,
                agent_name="EvidenceNormalizer",
            )
            if packets:
                ctx.event_bus.emit(
                    AgentEventType.evidence_collected,
                    "도구 결과가 evidence로 저장되었습니다.",
                    {
                        "count": len(packets),
                        "evidence_ids": [packet.evidence_id for packet in packets],
                    },
                )
                ctx.event_bus.emit(
                    AgentEventType.evidence_normalized,
                    "provider 결과가 표준 evidence packet으로 정규화되었습니다.",
                    {"categories": sorted({packet.category.value for packet in packets})},
                )
                ctx.event_bus.emit(
                    AgentEventType.evidence_ranked,
                    "evidence가 신뢰도와 freshness 기준으로 정렬되었습니다.",
                    {"count": len(packets)},
                )
            status = self._run_status_for_state(state)
            event_type = (
                AgentEventType.run_waiting_for_user
                if status == AgentRunStatus.waiting_for_user
                else AgentEventType.run_completed
            )
            ctx.event_bus.emit(
                event_type, self._run_status_message(status), {"status": status.value}
            )
            self.run_repository.update_run(
                ctx.run_id,
                status=status,
                current_step=None,
                completed_at=utc_now() if status == AgentRunStatus.completed else None,
            )
            ctx.checkpoint_store.save(state)
        except Exception as exc:
            self.run_repository.update_run(
                ctx.run_id,
                status=AgentRunStatus.failed,
                current_step=None,
                completed_at=utc_now(),
                error_message=str(exc),
            )
            ctx.event_bus.emit(
                AgentEventType.error, "에이전트 실행 중 오류가 발생했습니다.", {"error": str(exc)}
            )
            ctx.checkpoint_store.save(state)
            raise

    def _record_source_discovery(self, ctx: RunContext) -> None:
        domains = ["flights", "accommodations", "places", "routes", "activities", "visa", "safety"]
        for domain in domains:
            result = ctx.tool_executor.discover_sources(domain)
            if result["enabled"]:
                ctx.event_bus.emit(
                    AgentEventType.source_discovered,
                    f"{domain} source가 선택되었습니다.",
                    {"domain": domain, "sources": result["enabled"]},
                )
            for source in result["rejected"]:
                ctx.event_bus.emit(
                    AgentEventType.source_rejected,
                    f"{domain} source가 정책 또는 설정 때문에 제외되었습니다.",
                    {"domain": domain, "source": source},
                )

    def _run_status_for_state(self, state: TripPlanState) -> AgentRunStatus:
        if state.status == TripStatus.failed:
            return AgentRunStatus.failed
        if state.status == TripStatus.needs_user_input:
            return AgentRunStatus.waiting_for_user
        return AgentRunStatus.completed

    def _run_status_message(self, status: AgentRunStatus) -> str:
        if status == AgentRunStatus.waiting_for_user:
            return "추가 정보가 필요해 run이 대기 중입니다."
        if status == AgentRunStatus.completed:
            return "여행 계획 run이 완료되었습니다."
        return f"run 상태가 {status.value}로 변경되었습니다."

    def _detail_response(self, run: AgentRun, state: TripPlanState) -> AgentRunDetailResponse:
        return AgentRunDetailResponse(
            run=run,
            steps=self.run_repository.list_steps(run.run_id),
            events=self.run_repository.list_events(run.run_id),
            state_summary=self._state_summary(state),
            state=state,
        )

    def _state_summary(self, state: TripPlanState) -> TripStateSummary:
        brief = state.brief
        date_range = None
        if brief and brief.start_date and brief.end_date:
            date_range = f"{brief.start_date.isoformat()} ~ {brief.end_date.isoformat()}"
        travelers = None
        if brief:
            travelers = brief.traveler_count or brief.travelers
        return TripStateSummary(
            destination=state.selected_destination
            or (", ".join(brief.destinations) if brief and brief.destinations else None),
            origin=brief.origin if brief else None,
            date_range=date_range,
            travelers=travelers,
            budget_total=brief.budget_total if brief else None,
            budget_per_person=brief.budget_per_person if brief else None,
            status=state.status.value,
            missing_fields=state.missing_fields,
            assumptions=state.assumptions,
        )

    def _question_for(self, field: str) -> str:
        return {
            "origin": "어디에서 출발하시나요?",
            "destinations": "어디로 가고 싶으신가요?",
            "start_date": "언제 출발하시나요?",
            "end_date": "언제 돌아오시나요?",
            "travelers": "몇 명이 여행하시나요?",
            "passport_country": "여권 국적은 어디인가요?",
        }.get(field, f"{field} 정보가 필요합니다.")


class RuntimeRecorder(AgentRunRecorder):
    def __init__(self, *, trip_id: str, run_id: str, repository: AgentRunRepository) -> None:
        self.trip_id = trip_id
        self.run_id = run_id
        self.repository = repository

    def start_step(self, agent_name: str, input_summary: str) -> str:
        step_id = new_id("step")
        self.repository.update_run(
            self.run_id, status=AgentRunStatus.running, current_step=agent_name
        )
        self.repository.add_step(
            AgentStep(
                step_id=step_id,
                run_id=self.run_id,
                trip_id=self.trip_id,
                agent_name=agent_name,
                status=AgentStepStatus.running,
                input_summary=input_summary,
                started_at=utc_now(),
            )
        )
        self.event("agent_started", f"{agent_name} 시작", {"agent_name": agent_name})
        return step_id

    def complete_step(
        self, step_id: str, output_summary: str, tool_calls: list[dict] | None = None
    ) -> None:
        step = self.repository.update_step(
            step_id,
            status=AgentStepStatus.completed,
            output_summary=output_summary,
            completed_at=utc_now(),
            tool_calls=tool_calls or [],
        )
        if tool_calls:
            self.event(
                "tool_call_completed",
                f"{step.agent_name} 도구 호출 완료",
                {"agent_name": step.agent_name, "tool_calls": tool_calls},
            )
        self.event(
            "agent_completed",
            f"{step.agent_name} 완료",
            {"agent_name": step.agent_name, "output_summary": output_summary},
        )

    def skip_step(self, agent_name: str, reason: str) -> None:
        self.repository.add_step(
            AgentStep(
                step_id=new_id("step"),
                run_id=self.run_id,
                trip_id=self.trip_id,
                agent_name=agent_name,
                status=AgentStepStatus.skipped,
                input_summary=reason,
                output_summary=reason,
            )
        )
        self.event(
            "agent_skipped", f"{agent_name} 건너뜀", {"agent_name": agent_name, "reason": reason}
        )

    def fail_step(self, step_id: str, reason: str) -> None:
        step = self.repository.update_step(
            step_id,
            status=AgentStepStatus.failed,
            output_summary=reason,
            completed_at=utc_now(),
            error_message=reason,
        )
        self.event(
            "agent_failed",
            f"{step.agent_name} 실패",
            {"agent_name": step.agent_name, "reason": reason},
        )

    def event(self, event_type: str, message: str, payload: dict | None = None) -> None:
        self.repository.add_event(
            AgentEvent(
                event_id=new_id("event"),
                run_id=self.run_id,
                trip_id=self.trip_id,
                type=AgentEventType(event_type),
                message=message,
                payload=payload or {},
                created_at=utc_now(),
            )
        )
