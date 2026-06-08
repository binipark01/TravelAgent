from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "trips",
        sa.Column("trip_id", sa.String(length=80), nullable=False),
        sa.Column("user_id", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("current_snapshot_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("trip_id"),
    )
    op.create_index(op.f("ix_trips_user_id"), "trips", ["user_id"])
    op.create_index(op.f("ix_trips_status"), "trips", ["status"])
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=80), nullable=False),
        sa.Column("preferences_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_table(
        "trip_state_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trip_id", sa.String(length=80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.trip_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_trip_state_snapshots_trip_id"), "trip_state_snapshots", ["trip_id"])
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trip_id", sa.String(length=80), nullable=False),
        sa.Column("agent_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("input_json", sa.JSON(), nullable=True),
        sa.Column("output_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.trip_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_runs_trip_id"), "agent_runs", ["trip_id"])
    op.create_table(
        "source_refs",
        sa.Column("source_id", sa.String(length=80), nullable=False),
        sa.Column("trip_id", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("reference", sa.String(length=240), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_mock", sa.Integer(), nullable=False),
        sa.Column("freshness_note", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.trip_id"]),
        sa.PrimaryKeyConstraint("source_id"),
    )
    op.create_index(op.f("ix_source_refs_trip_id"), "source_refs", ["trip_id"])
    op.create_table(
        "approval_requests",
        sa.Column("approval_id", sa.String(length=80), nullable=False),
        sa.Column("trip_id", sa.String(length=80), nullable=False),
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("exact_payload_hash", sa.String(length=128), nullable=False),
        sa.Column("price_ceiling_amount", sa.Float(), nullable=True),
        sa.Column("price_ceiling_currency", sa.String(length=12), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.trip_id"]),
        sa.PrimaryKeyConstraint("approval_id"),
    )
    op.create_index(op.f("ix_approval_requests_trip_id"), "approval_requests", ["trip_id"])
    op.create_index(op.f("ix_approval_requests_status"), "approval_requests", ["status"])
    op.create_table(
        "booking_records",
        sa.Column("booking_id", sa.String(length=80), nullable=False),
        sa.Column("trip_id", sa.String(length=80), nullable=False),
        sa.Column("approval_id", sa.String(length=80), nullable=False),
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("provider_reference", sa.String(length=120), nullable=False),
        sa.Column("simulated", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("price_amount", sa.Float(), nullable=False),
        sa.Column("price_currency", sa.String(length=12), nullable=False),
        sa.Column("notes_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approval_id"], ["approval_requests.approval_id"]),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.trip_id"]),
        sa.PrimaryKeyConstraint("booking_id"),
    )
    op.create_index(op.f("ix_booking_records_trip_id"), "booking_records", ["trip_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_booking_records_trip_id"), table_name="booking_records")
    op.drop_table("booking_records")
    op.drop_index(op.f("ix_approval_requests_status"), table_name="approval_requests")
    op.drop_index(op.f("ix_approval_requests_trip_id"), table_name="approval_requests")
    op.drop_table("approval_requests")
    op.drop_index(op.f("ix_source_refs_trip_id"), table_name="source_refs")
    op.drop_table("source_refs")
    op.drop_index(op.f("ix_agent_runs_trip_id"), table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index(op.f("ix_trip_state_snapshots_trip_id"), table_name="trip_state_snapshots")
    op.drop_table("trip_state_snapshots")
    op.drop_table("user_preferences")
    op.drop_index(op.f("ix_trips_status"), table_name="trips")
    op.drop_index(op.f("ix_trips_user_id"), table_name="trips")
    op.drop_table("trips")
    op.drop_table("users")
