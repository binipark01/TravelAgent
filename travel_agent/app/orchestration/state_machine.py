from __future__ import annotations

from collections.abc import Iterable

from travel_agent.app.schemas.common import AuditEvent, SourceRef, TripStatus
from travel_agent.app.schemas.trip import TripPlanState
from travel_agent.app.utils.ids import new_id
from travel_agent.app.utils.time import utc_now

CRITICAL_FIELDS = ["destinations"]


def add_audit_event(
    state: TripPlanState, event_type: str, message: str, actor: str = "system"
) -> None:
    state.audit_log.append(
        AuditEvent(
            event_id=new_id("audit"),
            event_type=event_type,
            message=message,
            created_at=utc_now(),
            actor=actor,
        )
    )


def set_status(state: TripPlanState, status: TripStatus, message: str) -> None:
    if state.status != status:
        state.status = status
        add_audit_event(state, "status_changed", message)


def append_source_refs(state: TripPlanState, refs: Iterable[SourceRef]) -> None:
    existing = {ref.source_id for ref in state.source_refs}
    for ref in refs:
        if ref.source_id not in existing:
            state.source_refs.append(ref)
            existing.add(ref.source_id)


def critical_missing_fields(state: TripPlanState) -> list[str]:
    return [field for field in CRITICAL_FIELDS if field in state.missing_fields]


def questions_for_missing(fields: list[str]) -> list[str]:
    question_map = {
        "origin": "출발지는 어디인가요?",
        "destinations": "가고 싶은 목적지나 후보 국가는 어디인가요?",
        "start_date": "출발 날짜는 언제인가요?",
        "end_date": "귀국 또는 여행 종료 날짜는 언제인가요?",
        "travelers": "여행 인원은 몇 명인가요?",
    }
    return [question_map[field] for field in fields if field in question_map]
