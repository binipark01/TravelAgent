from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import create_ready_trip


def test_trip_creation_endpoint(client: TestClient, base_trip_payload: dict) -> None:
    response = client.post("/trips", json=base_trip_payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "needs_user_input"
    assert set(data["missing_fields"]) == {"origin", "passport_country"}


def test_cors_allows_local_vite_origin(client: TestClient) -> None:
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_message_merge_update_endpoint(client: TestClient, base_trip_payload: dict) -> None:
    trip_id = create_ready_trip(client, base_trip_payload)
    response = client.get(f"/trips/{trip_id}")

    assert response.status_code == 200
    state = response.json()["state"]
    assert state["brief"]["origin"] == "서울"
    assert state["brief"]["start_date"] == "2026-10-03"
    assert state["brief"]["end_date"] == "2026-10-07"
    assert state["missing_fields"] == []


def test_full_planning_endpoint_with_mock_providers(
    client: TestClient, base_trip_payload: dict
) -> None:
    trip_id = create_ready_trip(client, base_trip_payload)
    response = client.post(f"/trips/{trip_id}/plan")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["recommended_destination"] in {"Osaka", "Tokyo", "Fukuoka"}
    assert data["itinerary"]["days"]
    assert data["budget"]["total_estimated_cost"] > 0
    assert data["critic_findings"]
    assert data["source_refs"]
    assert all(ref["is_mock"] for ref in data["source_refs"])
