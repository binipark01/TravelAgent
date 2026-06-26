from __future__ import annotations

from datetime import UTC, datetime

from travel_agent.app.agent_core.runtime import _latency_ms
from travel_agent.app.db.types import UtcDateTime
from travel_agent.app.schemas.agent import AgentStep, AgentStepStatus


def test_utcdatetime_result_value_is_aware() -> None:
    col = UtcDateTime()
    # SQLite는 naive를 돌려주지만 result 처리에서 aware-UTC로 정규화돼야 한다.
    naive = datetime(2026, 6, 26, 12, 0, 0)
    out = col.process_result_value(naive, None)
    assert out is not None and out.tzinfo is not None
    assert out == datetime(2026, 6, 26, 12, 0, 0, tzinfo=UTC)
    # 이미 aware면 UTC로 환산해 유지.
    aware = datetime(2026, 6, 26, 21, 0, 0, tzinfo=UTC)
    assert col.process_result_value(aware, None) == aware
    # None은 그대로.
    assert col.process_result_value(None, None) is None


def test_utcdatetime_bind_value_is_aware() -> None:
    col = UtcDateTime()
    naive = datetime(2026, 6, 26, 12, 0, 0)
    bound = col.process_bind_param(naive, None)
    assert bound is not None and bound.tzinfo is not None  # 저장 전 aware-UTC로 정규화
    assert col.process_bind_param(None, None) is None


def test_latency_ms_no_longer_mismatches_after_normalization() -> None:
    # 정규화 후엔 started_at·completed_at이 모두 aware-UTC라 latency가 정상 계산된다.
    step = AgentStep(
        step_id="step_1",
        run_id="run_1",
        trip_id="trip_1",
        agent_name="FlightAgent",
        status=AgentStepStatus.completed,
        input_summary="in",
        started_at=datetime(2026, 6, 26, 12, 0, 0, tzinfo=UTC),
        completed_at=datetime(2026, 6, 26, 12, 0, 2, 500000, tzinfo=UTC),
    )
    assert _latency_ms(step) == 2500


def test_latency_ms_guard_returns_none_on_mismatch() -> None:
    # 가드는 유지된다 — 어떤 이유로 naive/aware가 혼재해도 예외 대신 None.
    step = AgentStep(
        step_id="step_2",
        run_id="run_1",
        trip_id="trip_1",
        agent_name="X",
        status=AgentStepStatus.completed,
        input_summary="in",
        started_at=datetime(2026, 6, 26, 12, 0, 0),  # naive
        completed_at=datetime(2026, 6, 26, 12, 0, 1, tzinfo=UTC),  # aware
    )
    assert _latency_ms(step) is None
