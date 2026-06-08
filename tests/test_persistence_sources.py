from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.conftest import create_ready_trip
from travel_agent.app.db.models import TripStateSnapshotModel
from travel_agent.app.db.session import get_session_factory


def test_trip_plan_state_snapshots_persist(client: TestClient, base_trip_payload: dict) -> None:
    trip_id = create_ready_trip(client, base_trip_payload)

    factory = get_session_factory()
    with factory() as session:
        count = len(
            session.execute(
                select(TripStateSnapshotModel).where(TripStateSnapshotModel.trip_id == trip_id)
            )
            .scalars()
            .all()
        )

    assert count >= 2


def test_source_refs_included_in_provider_outputs(
    client: TestClient, base_trip_payload: dict
) -> None:
    trip_id = create_ready_trip(client, base_trip_payload)
    response = client.post(f"/trips/{trip_id}/plan")

    assert response.status_code == 200
    source_refs = response.json()["source_refs"]
    assert source_refs
    assert {ref["provider"] for ref in source_refs} >= {
        "mock_flights",
        "mock_accommodation",
        "mock_places",
    }
