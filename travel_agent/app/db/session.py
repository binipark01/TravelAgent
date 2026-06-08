from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from travel_agent.app.config import get_settings
from travel_agent.app.db.base import Base

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def configure_database(database_url: str | None = None) -> None:
    global _engine, _session_factory
    url = database_url or get_settings().database_url
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if url.endswith(":memory:"):
            kwargs["poolclass"] = StaticPool
    _engine = create_engine(url, future=True, **kwargs)
    _session_factory = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        configure_database()
    assert _engine is not None
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        configure_database()
    assert _session_factory is not None
    return _session_factory


def init_db() -> None:
    from travel_agent.app.db import models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())
    _ensure_agent_run_columns()
    _ensure_agent_step_columns()
    _ensure_source_ref_columns()
    _ensure_trip_snapshot_columns()


def _ensure_agent_run_columns() -> None:
    engine = get_engine()
    inspector = inspect(engine)
    if "agent_runs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("agent_runs")}
    additions = {
        "run_id": "VARCHAR(80)",
        "current_step": "VARCHAR(120)",
        "started_at": "DATETIME",
        "completed_at": "DATETIME",
        "error_message": "TEXT",
    }
    with engine.begin() as connection:
        for name, ddl in additions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE agent_runs ADD COLUMN {name} {ddl}"))


def _add_missing_columns(table_name: str, additions: dict[str, str]) -> None:
    engine = get_engine()
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    with engine.begin() as connection:
        for name, ddl in additions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {name} {ddl}"))


def _ensure_agent_step_columns() -> None:
    _add_missing_columns(
        "agent_steps",
        {
            "trip_id": "VARCHAR(80)",
            "error_message": "TEXT",
        },
    )


def _ensure_source_ref_columns() -> None:
    _add_missing_columns(
        "source_refs",
        {
            "run_id": "VARCHAR(80)",
            "provider_ref": "VARCHAR(240)",
            "source_url": "VARCHAR(500)",
            "is_live": "INTEGER DEFAULT 0",
            "source_type": "VARCHAR(80) DEFAULT 'mock'",
            "confidence": "FLOAT DEFAULT 0.5",
            "attribution": "TEXT",
            "license_notes": "TEXT",
        },
    )


def _ensure_trip_snapshot_columns() -> None:
    _add_missing_columns("trip_state_snapshots", {"run_id": "VARCHAR(80)"})


def get_db() -> Generator[Session, None, None]:
    factory = get_session_factory()
    with factory() as session:
        yield session
