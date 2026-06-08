from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from travel_agent.app.db.models import (
    AgentEventModel,
    AgentRunModel,
    AgentStepModel,
    ApprovalRequestModel,
    BookingRecordModel,
    SourceRefModel,
    TripModel,
    TripStateSnapshotModel,
    UserModel,
)
from travel_agent.app.schemas.agent import (
    AgentEvent,
    AgentEventType,
    AgentRun,
    AgentRunStatus,
    AgentStep,
    AgentStepStatus,
)
from travel_agent.app.schemas.approvals import ApprovalRequest, ApprovalStatus, BookingRecord
from travel_agent.app.schemas.common import Money, TripStatus
from travel_agent.app.schemas.trip import TripPlanState


class NotFoundError(Exception):
    pass


class AgentRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_run(self, run: AgentRun) -> None:
        self.session.add(
            AgentRunModel(
                run_id=run.run_id,
                trip_id=run.trip_id,
                agent_name="TravelSupervisorAgent",
                status=run.status.value,
                current_step=run.current_step,
                input_json={},
                output_json={},
                started_at=run.started_at,
                completed_at=run.completed_at,
                error_message=run.error_message,
            )
        )
        self.session.flush()

    def get_run(self, run_id: str) -> AgentRun:
        model = self._get_run_model(run_id)
        return self._to_run(model)

    def list_runs(self, limit: int = 30) -> list[AgentRun]:
        stmt = (
            select(AgentRunModel).order_by(AgentRunModel.started_at.desc()).limit(limit)
        )
        return [self._to_run(model) for model in self.session.execute(stmt).scalars()]

    def update_run(
        self,
        run_id: str,
        *,
        status: AgentRunStatus,
        current_step: str | None = None,
        completed_at=None,
        error_message: str | None = None,
    ) -> AgentRun:
        model = self._get_run_model(run_id)
        model.status = status.value
        model.current_step = current_step
        model.completed_at = completed_at
        model.error_message = error_message
        return self._to_run(model)

    def add_step(self, step: AgentStep) -> None:
        self.session.add(
            AgentStepModel(
                step_id=step.step_id,
                run_id=step.run_id,
                trip_id=step.trip_id,
                agent_name=step.agent_name,
                status=step.status.value,
                input_summary=step.input_summary,
                output_summary=step.output_summary,
                tool_calls_json=step.tool_calls,
                started_at=step.started_at,
                completed_at=step.completed_at,
                error_message=step.error_message,
            )
        )
        self.session.flush()

    def update_step(
        self,
        step_id: str,
        *,
        status: AgentStepStatus,
        output_summary: str | None = None,
        completed_at=None,
        tool_calls: list[dict] | None = None,
        error_message: str | None = None,
    ) -> AgentStep:
        model = self._get_step_model(step_id)
        model.status = status.value
        if output_summary is not None:
            model.output_summary = output_summary
        if completed_at is not None:
            model.completed_at = completed_at
        if tool_calls is not None:
            model.tool_calls_json = tool_calls
        if error_message is not None:
            model.error_message = error_message
        return self._to_step(model)

    def list_steps(self, run_id: str) -> list[AgentStep]:
        stmt = (
            select(AgentStepModel)
            .where(AgentStepModel.run_id == run_id)
            .order_by(AgentStepModel.id)
        )
        return [self._to_step(model) for model in self.session.execute(stmt).scalars()]

    def add_event(self, event: AgentEvent) -> None:
        self.session.add(
            AgentEventModel(
                event_id=event.event_id,
                run_id=event.run_id,
                trip_id=event.trip_id,
                type=event.type.value,
                message=event.message,
                payload_json=event.payload,
                created_at=event.created_at,
            )
        )
        self.session.flush()

    def list_events(self, run_id: str) -> list[AgentEvent]:
        stmt = (
            select(AgentEventModel)
            .where(AgentEventModel.run_id == run_id)
            .order_by(AgentEventModel.id)
        )
        return [self._to_event(model) for model in self.session.execute(stmt).scalars()]

    def _get_run_model(self, run_id: str) -> AgentRunModel:
        stmt = select(AgentRunModel).where(AgentRunModel.run_id == run_id)
        model = self.session.execute(stmt).scalar_one_or_none()
        if not model:
            raise NotFoundError(f"Agent run not found: {run_id}")
        return model

    def _get_step_model(self, step_id: str) -> AgentStepModel:
        stmt = select(AgentStepModel).where(AgentStepModel.step_id == step_id)
        model = self.session.execute(stmt).scalar_one_or_none()
        if not model:
            raise NotFoundError(f"Agent step not found: {step_id}")
        return model

    def _to_run(self, model: AgentRunModel) -> AgentRun:
        return AgentRun(
            run_id=model.run_id,
            trip_id=model.trip_id,
            status=AgentRunStatus(model.status),
            current_step=model.current_step,
            started_at=model.started_at or model.created_at,
            completed_at=model.completed_at,
            error_message=model.error_message,
        )

    def _to_step(self, model: AgentStepModel) -> AgentStep:
        return AgentStep(
            step_id=model.step_id,
            run_id=model.run_id,
            trip_id=model.trip_id,
            agent_name=model.agent_name,
            status=AgentStepStatus(model.status),
            input_summary=model.input_summary,
            output_summary=model.output_summary,
            started_at=model.started_at,
            completed_at=model.completed_at,
            error_message=model.error_message,
            tool_calls=model.tool_calls_json or [],
        )

    def _to_event(self, model: AgentEventModel) -> AgentEvent:
        return AgentEvent(
            event_id=model.event_id,
            run_id=model.run_id,
            trip_id=model.trip_id,
            type=AgentEventType(model.type),
            message=model.message,
            payload=model.payload_json or {},
            created_at=model.created_at,
        )


class TripRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_trip(self, state: TripPlanState) -> None:
        if state.user_id and self.session.get(UserModel, state.user_id) is None:
            self.session.add(UserModel(user_id=state.user_id))
        trip = TripModel(
            trip_id=state.trip_id,
            user_id=state.user_id,
            status=state.status.value,
            current_snapshot_version=0,
        )
        self.session.add(trip)
        self.session.flush()
        self.save_snapshot(state)

    def get_trip(self, trip_id: str) -> TripModel:
        trip = self.session.get(TripModel, trip_id)
        if not trip:
            raise NotFoundError(f"Trip not found: {trip_id}")
        return trip

    def load_latest_state(self, trip_id: str) -> TripPlanState:
        trip = self.get_trip(trip_id)
        stmt = (
            select(TripStateSnapshotModel)
            .where(TripStateSnapshotModel.trip_id == trip_id)
            .order_by(TripStateSnapshotModel.version.desc())
            .limit(1)
        )
        snapshot = self.session.execute(stmt).scalar_one_or_none()
        if not snapshot:
            raise NotFoundError(f"Trip snapshot not found: {trip_id}")
        state = TripPlanState.model_validate(snapshot.state_json)
        state.status = TripStatus(trip.status)
        return state

    def save_snapshot(self, state: TripPlanState) -> int:
        trip = self.get_trip(state.trip_id)
        version = trip.current_snapshot_version + 1
        snapshot = TripStateSnapshotModel(
            trip_id=state.trip_id,
            version=version,
            state_json=state.model_dump(mode="json"),
        )
        trip.current_snapshot_version = version
        trip.status = state.status.value if hasattr(state.status, "value") else str(state.status)
        self.session.add(snapshot)
        self._sync_source_refs(state)
        return version

    def _sync_source_refs(self, state: TripPlanState) -> None:
        for ref in state.source_refs:
            if self.session.get(SourceRefModel, ref.source_id):
                continue
            self.session.add(
                SourceRefModel(
                    source_id=ref.source_id,
                    trip_id=state.trip_id,
                    provider=ref.provider,
                    provider_ref=ref.provider_ref,
                    source_url=ref.source_url,
                    title=ref.title,
                    reference=ref.reference,
                    retrieved_at=ref.retrieved_at,
                    expires_at=ref.expires_at,
                    is_live=1 if ref.is_live else 0,
                    is_mock=1 if ref.is_mock else 0,
                    source_type=ref.source_type,
                    confidence=ref.confidence,
                    attribution=ref.attribution,
                    license_notes=ref.license_notes,
                    freshness_note=ref.freshness_note,
                )
            )


class ApprovalRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, approval: ApprovalRequest) -> None:
        self.session.add(
            ApprovalRequestModel(
                approval_id=approval.approval_id,
                trip_id=approval.trip_id,
                action_type=approval.action_type,
                summary=approval.summary,
                exact_payload_hash=approval.exact_payload_hash,
                price_ceiling_amount=approval.price_ceiling.amount
                if approval.price_ceiling
                else None,
                price_ceiling_currency=approval.price_ceiling.currency
                if approval.price_ceiling
                else None,
                expires_at=approval.expires_at,
                status=approval.status.value,
                approved_at=approval.approved_at,
                rejected_at=approval.rejected_at,
            )
        )

    def get(self, approval_id: str) -> ApprovalRequest:
        model = self.session.get(ApprovalRequestModel, approval_id)
        if not model:
            raise NotFoundError(f"Approval not found: {approval_id}")
        return self._to_schema(model)

    def list_for_trip(self, trip_id: str) -> list[ApprovalRequest]:
        stmt = select(ApprovalRequestModel).where(ApprovalRequestModel.trip_id == trip_id)
        return [self._to_schema(model) for model in self.session.execute(stmt).scalars()]

    def update(self, approval: ApprovalRequest) -> None:
        model = self.session.get(ApprovalRequestModel, approval.approval_id)
        if not model:
            raise NotFoundError(f"Approval not found: {approval.approval_id}")
        model.status = approval.status.value
        model.approved_at = approval.approved_at
        model.rejected_at = approval.rejected_at

    def _to_schema(self, model: ApprovalRequestModel) -> ApprovalRequest:
        price_ceiling = None
        if model.price_ceiling_amount is not None and model.price_ceiling_currency:
            price_ceiling = Money(
                amount=model.price_ceiling_amount,
                currency=model.price_ceiling_currency,
            )
        return ApprovalRequest(
            approval_id=model.approval_id,
            trip_id=model.trip_id,
            action_type=model.action_type,
            summary=model.summary,
            exact_payload_hash=model.exact_payload_hash,
            price_ceiling=price_ceiling,
            expires_at=model.expires_at,
            status=ApprovalStatus(model.status),
            approved_at=model.approved_at,
            rejected_at=model.rejected_at,
        )


class BookingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, record: BookingRecord) -> None:
        self.session.add(
            BookingRecordModel(
                booking_id=record.booking_id,
                trip_id=record.trip_id,
                approval_id=record.approval_id,
                action_type=record.action_type,
                provider_reference=record.provider_reference,
                simulated=1 if record.simulated else 0,
                status=record.status,
                price_amount=record.price.amount,
                price_currency=record.price.currency,
                notes_json=record.notes,
                created_at=record.created_at,
            )
        )

    def list_for_trip(self, trip_id: str) -> list[BookingRecord]:
        stmt = select(BookingRecordModel).where(BookingRecordModel.trip_id == trip_id)
        return [self._to_schema(model) for model in self.session.execute(stmt).scalars()]

    def _to_schema(self, model: BookingRecordModel) -> BookingRecord:
        return BookingRecord(
            booking_id=model.booking_id,
            trip_id=model.trip_id,
            approval_id=model.approval_id,
            action_type=model.action_type,
            provider_reference=model.provider_reference,
            simulated=bool(model.simulated),
            status=model.status,
            price=Money(amount=model.price_amount, currency=model.price_currency),
            created_at=model.created_at,
            notes=model.notes_json,
        )
