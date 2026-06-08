from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from travel_agent.app.db.base import Base
from travel_agent.app.utils.time import utc_now


class UserModel(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    preferences: Mapped[UserPreferenceModel | None] = relationship(back_populates="user")


class UserPreferenceModel(Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), unique=True)
    preferences_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    user: Mapped[UserModel] = relationship(back_populates="preferences")


class TripModel(Base):
    __tablename__ = "trips"

    trip_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    current_snapshot_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    snapshots: Mapped[list[TripStateSnapshotModel]] = relationship(back_populates="trip")


class TripStateSnapshotModel(Base):
    __tablename__ = "trip_state_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.trip_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer)
    state_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    trip: Mapped[TripModel] = relationship(back_populates="snapshots")


class AgentRunModel(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.trip_id"), index=True)
    agent_name: Mapped[str] = mapped_column(String(120), default="TravelSupervisorAgent")
    status: Mapped[str] = mapped_column(String(40))
    current_step: Mapped[str | None] = mapped_column(String(120), nullable=True)
    input_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentStepModel(Base):
    __tablename__ = "agent_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    step_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    run_id: Mapped[str] = mapped_column(String(80), index=True)
    trip_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    agent_name: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    input_summary: Mapped[str] = mapped_column(Text)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_calls_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ToolCallModel(Base):
    __tablename__ = "tool_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(80), index=True)
    step_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    trip_id: Mapped[str] = mapped_column(String(80), index=True)
    tool_name: Mapped[str] = mapped_column(String(160), index=True)
    provider: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    input_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentEventModel(Base):
    __tablename__ = "agent_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    run_id: Mapped[str] = mapped_column(String(80), index=True)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.trip_id"), index=True)
    type: Mapped[str] = mapped_column(String(80), index=True)
    message: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SourceRefModel(Base):
    __tablename__ = "source_refs"

    source_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.trip_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(120))
    provider_ref: Mapped[str | None] = mapped_column(String(240), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    title: Mapped[str] = mapped_column(String(240))
    reference: Mapped[str] = mapped_column(String(240))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_live: Mapped[int] = mapped_column(Integer, default=0)
    is_mock: Mapped[int] = mapped_column(Integer, default=1)
    source_type: Mapped[str] = mapped_column(String(80), default="mock")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    attribution: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    freshness_note: Mapped[str] = mapped_column(Text)


class EvidencePacketModel(Base):
    __tablename__ = "evidence_packets"

    evidence_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    trip_id: Mapped[str] = mapped_column(String(80), index=True)
    run_id: Mapped[str] = mapped_column(String(80), index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    normalized_data_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    source_refs_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    collected_by_agent: Mapped[str] = mapped_column(String(120), index=True)
    collected_by_tool: Mapped[str] = mapped_column(String(160), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    freshness_policy: Mapped[str] = mapped_column(String(120))
    confidence: Mapped[float] = mapped_column(Float, default=0.5)


class ApprovalRequestModel(Base):
    __tablename__ = "approval_requests"

    approval_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.trip_id"), index=True)
    action_type: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(Text)
    exact_payload_hash: Mapped[str] = mapped_column(String(128))
    price_ceiling_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_ceiling_currency: Mapped[str | None] = mapped_column(String(12), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40), index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class BookingRecordModel(Base):
    __tablename__ = "booking_records"

    booking_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.trip_id"), index=True)
    approval_id: Mapped[str] = mapped_column(ForeignKey("approval_requests.approval_id"))
    action_type: Mapped[str] = mapped_column(String(80))
    provider_reference: Mapped[str] = mapped_column(String(120))
    simulated: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(40))
    price_amount: Mapped[float] = mapped_column(Float)
    price_currency: Mapped[str] = mapped_column(String(12))
    notes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
