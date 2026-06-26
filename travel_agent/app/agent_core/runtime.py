from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from travel_agent.app.agent_core.cancellation import (
    RunCancelled,
    request_cancel,
)
from travel_agent.app.agent_core.cancellation import (
    clear as clear_cancel,
)
from travel_agent.app.agent_core.checkpoint import CheckpointStore
from travel_agent.app.agent_core.event_bus import EventBus
from travel_agent.app.agent_core.run_context import RunContext
from travel_agent.app.agents.supervisor import TravelSupervisorAgent as LegacyPlanningSupervisor
from travel_agent.app.config import Settings, get_settings
from travel_agent.app.db.repositories import AgentRunRepository, TripRepository
from travel_agent.app.evidence.store import EvidenceStore
from travel_agent.app.llm.direct_answer import build_answer_client, is_conversational_question
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
from travel_agent.app.schemas.itinerary import Itinerary
from travel_agent.app.schemas.trip import TripPlanState
from travel_agent.app.sources.registry import SourceRegistry
from travel_agent.app.sources.source_discovery import SourceDiscoveryTool
from travel_agent.app.tools.travel_tools import ToolExecutor
from travel_agent.app.utils.ids import new_id
from travel_agent.app.utils.time import utc_now

logger = logging.getLogger(__name__)


def _latency_ms(step: AgentStep) -> int | None:
    """단계 소요시간(ms). started_at·completed_at이 있을 때만. (관측 로그 전용, shape 불변).

    이제 모든 DB datetime이 UtcDateTime으로 aware-UTC 통일돼 naive/aware 혼재는 없지만,
    관측용이라 어떤 이유로도 예외를 던지면 안 되므로 방어 가드는 유지한다(실패 시 None).
    """
    if step.started_at is None or step.completed_at is None:
        return None
    try:
        return int((step.completed_at - step.started_at).total_seconds() * 1000)
    except (TypeError, ValueError):
        return None


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

    def begin_run(
        self,
        message: str,
        *,
        user_id: str | None = None,
        locale: str = "ko-KR",
        currency: str = "KRW",
        timezone: str = "Asia/Seoul",
        history: list[str] | None = None,
    ) -> AgentRunResponse:
        """run/trip을 만들고 run_id를 즉시 돌려준다. 무거운 실행은 execute_run이 맡는다."""
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
        self.session.commit()
        persisted_run = self.run_repository.get_run(run.run_id)
        return self._run_response(persisted_run, state)

    def execute_run(self, run_id: str, *, message: str | None = None) -> AgentRunResponse:
        """begin_run/begin_continue로 만들어진 run을 실제로 실행한다(백그라운드 태스크용)."""
        run = self.run_repository.get_run(run_id)
        state = self.trip_repository.load_latest_state(run.trip_id)
        ctx = self._build_context(run_id, state)
        # 정보를 묻는 대화형 질문이면 계획 파이프라인 대신 LLM이 바로 답한다.
        intake_message = message or state.raw_user_message
        if self.settings.enable_live_llm and is_conversational_question(intake_message):
            self._answer_conversationally(ctx, state, intake_message)
            self.session.commit()
            persisted_run = self.run_repository.get_run(run_id)
            return self._run_response(persisted_run, state)
        try:
            self._execute(ctx, state, message=message)
        except Exception:
            # _execute가 실패 상태/에러 이벤트를 기록했으니 영속화해 폴링이 실패를 본다.
            self.session.commit()
            raise
        self.session.commit()
        persisted_run = self.run_repository.get_run(run_id)
        return self._run_response(persisted_run, state)

    def _answer_conversationally(
        self, ctx: RunContext, state: TripPlanState, message: str
    ) -> None:
        """계획 대신 LLM이 질문에 바로 답해 state.assistant_message에 채운다."""
        state.assistant_message = None
        recorder = RuntimeRecorder(
            trip_id=state.trip_id,
            run_id=ctx.run_id,
            repository=self.run_repository,
            state=state,
            checkpoint_store=ctx.checkpoint_store,
            session=self.session,
        )
        # 느린 LLM 호출 전에 '진행 중'을 커밋해 폴링이 답변 작성 중임을 보게 한다.
        step_id = recorder.start_step("TravelAdvisorAgent", "여행 질문에 답변")
        try:
            client = build_answer_client(self.settings)
            answer = client.answer(
                message=message,
                locale=state.locale,
                currency=state.currency,
                timezone=state.timezone,
            )
            state.assistant_message = answer.strip() or "답변을 생성하지 못했어요."
            recorder.complete_step(step_id, "답변 생성 완료")
        except Exception as exc:  # noqa: BLE001 - 실패해도 run은 메시지와 함께 완료시킨다
            state.assistant_message = "지금 답변을 생성하지 못했어요. 잠시 후 다시 시도해 주세요."
            recorder.fail_step(step_id, str(exc))
        ctx.event_bus.emit(
            AgentEventType.plan_ready, "답변이 준비되었습니다.", {"trip_id": state.trip_id}
        )
        self.run_repository.update_run(
            ctx.run_id,
            status=AgentRunStatus.completed,
            current_step=None,
            completed_at=utc_now(),
        )
        ctx.checkpoint_store.save(state)

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
        """동기 경로: begin + execute를 한 번에 수행해 완성된 응답을 반환한다."""
        started = self.begin_run(
            message,
            user_id=user_id,
            locale=locale,
            currency=currency,
            timezone=timezone,
            history=history,
        )
        return self.execute_run(started.run_id)

    def begin_continue(
        self, run_id: str, user_message: str | None = None
    ) -> AgentRunDetailResponse:
        """이어가기 턴을 준비한다: 메시지 반영 + run을 running으로 표시하고 즉시 반환."""
        run = self.run_repository.get_run(run_id)
        state = self.trip_repository.load_latest_state(run.trip_id)
        ctx = self._build_context(run_id, state)
        if user_message:
            state.raw_user_message = f"{state.raw_user_message}\n{user_message}"
            state.raw_user_messages.append(user_message)
            add_audit_event(
                state,
                "message_added",
                "User supplied additional agent details.",
                actor="user",
            )
            ctx.event_bus.emit(
                AgentEventType.user_message,
                "사용자가 추가 정보를 입력했습니다.",
                {"message": user_message},
            )
        self.run_repository.update_run(run_id, status=AgentRunStatus.running, current_step=None)
        # 추가 메시지가 반영된 스냅샷을 저장해 execute_run/폴링이 최신 상태를 읽게 한다.
        ctx.checkpoint_store.save(state)
        self.session.commit()
        return self.get_run(run_id)

    def continue_run(self, run_id: str, user_message: str | None = None) -> AgentRunDetailResponse:
        """동기 경로: 이어가기 준비 + 실행을 한 번에 수행한다."""
        self.begin_continue(run_id, user_message)
        self.execute_run(run_id, message=user_message)
        return self.get_run(run_id)

    def _run_response(self, run: AgentRun, state: TripPlanState) -> AgentRunResponse:
        return AgentRunResponse(
            trip_id=state.trip_id,
            run_id=run.run_id,
            status=run.status,
            current_step=run.current_step,
            steps=self.run_repository.list_steps(run.run_id),
            missing_fields=state.missing_fields,
            questions=[self._question_for(field) for field in state.missing_fields],
            state_summary=self._state_summary(state),
            partial_plan=state,
            events=self.run_repository.list_events(run.run_id),
        )

    def get_run(self, run_id: str) -> AgentRunDetailResponse:
        run = self.run_repository.get_run(run_id)
        state = self.trip_repository.load_latest_state(run.trip_id)
        return self._detail_response(run, state)

    def cancel_run(self, run_id: str) -> AgentRunDetailResponse:
        """실행 중지: 협조적 취소 플래그를 세워 백그라운드 실행이 다음 단계 경계에서 멈추게
        하고, 아직 진행 중이면 상태를 즉시 cancelled로 표시해 화면이 바로 반응하게 한다."""
        run = self.run_repository.get_run(run_id)  # 없으면 404
        request_cancel(run_id)
        if run.status in (AgentRunStatus.queued, AgentRunStatus.running):
            self.run_repository.update_run(
                run_id,
                status=AgentRunStatus.cancelled,
                current_step=None,
                completed_at=utc_now(),
            )
            self.session.commit()
        return self.get_run(run_id)

    def update_itinerary(self, run_id: str, itinerary: Itinerary) -> AgentRunDetailResponse:
        """사용자가 화면에서 직접 편집한 일정을 저장한다(드래그·삭제·시간 수정)."""
        run = self.run_repository.get_run(run_id)
        state = self.trip_repository.load_latest_state(run.trip_id)
        state.optimized_itinerary = itinerary
        state.draft_itinerary = itinerary
        self.trip_repository.save_snapshot(state)
        self.session.commit()
        return self.get_run(run_id)

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
        # 계획 파이프라인이면 이전 대화형 답변은 지운다(요약이 답변으로 덮이지 않게).
        state.assistant_message = None
        recorder = RuntimeRecorder(
            trip_id=state.trip_id,
            run_id=ctx.run_id,
            repository=self.run_repository,
            state=state,
            checkpoint_store=ctx.checkpoint_store,
            session=self.session,
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
        except RunCancelled:
            # 사용자가 중지를 요청함 — 실패가 아니라 '취소'로 마무리하고 부분 결과를 남긴다.
            self.run_repository.update_run(
                ctx.run_id,
                status=AgentRunStatus.cancelled,
                current_step=None,
                completed_at=utc_now(),
            )
            ctx.event_bus.emit(
                AgentEventType.run_completed,
                "사용자가 실행을 중지했습니다.",
                {"status": AgentRunStatus.cancelled.value},
            )
            ctx.checkpoint_store.save(state)
            clear_cancel(ctx.run_id)
            return
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
    def __init__(
        self,
        *,
        trip_id: str,
        run_id: str,
        repository: AgentRunRepository,
        state: TripPlanState | None = None,
        checkpoint_store: CheckpointStore | None = None,
        session: Session | None = None,
    ) -> None:
        self.trip_id = trip_id
        self.run_id = run_id
        self.repository = repository
        # 아래 셋이 모두 있으면 에이전트마다 부분 상태를 저장+커밋해
        # 폴링하는 클라이언트가 '되는 것부터' 볼 수 있게 한다.
        self.state = state
        self.checkpoint_store = checkpoint_store
        self.session = session

    def _flush(self, *, checkpoint: bool) -> None:
        if checkpoint and self.checkpoint_store is not None and self.state is not None:
            self.checkpoint_store.save(self.state)
        if self.session is not None:
            self.session.commit()

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
        # 시작 시점에 진행 표시(현재 단계)를 바로 보이게 커밋한다(상태 저장은 불필요).
        self._flush(checkpoint=False)
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
        # 관측: 단계 소요시간을 로그로만 남긴다(응답 shape 불변).
        logger.info("step 완료 agent=%s latency_ms=%s", step.agent_name, _latency_ms(step))
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
        # 누적된 부분 결과를 스냅샷으로 저장 + 커밋 → 폴링이 즉시 본다.
        self._flush(checkpoint=True)

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
        self._flush(checkpoint=True)

    def fail_step(self, step_id: str, reason: str) -> None:
        step = self.repository.update_step(
            step_id,
            status=AgentStepStatus.failed,
            output_summary=reason,
            completed_at=utc_now(),
            error_message=reason,
        )
        # 관측: 실패 단계의 소요시간·사유를 로그로 남긴다(응답 shape 불변).
        logger.info(
            "step 실패 agent=%s latency_ms=%s reason=%s",
            step.agent_name, _latency_ms(step), reason,
        )
        self.event(
            "agent_failed",
            f"{step.agent_name} 실패",
            {"agent_name": step.agent_name, "reason": reason},
        )
        self._flush(checkpoint=True)

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
