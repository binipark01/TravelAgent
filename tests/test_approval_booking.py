from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import create_ready_trip


def test_approval_required_before_booking(client: TestClient, base_trip_payload: dict) -> None:
    trip_id = create_ready_trip(client, base_trip_payload)
    response = client.post(
        f"/trips/{trip_id}/bookings/simulate",
        json={
            "action_type": "booking",
            "payload": {
                "hotel_option_id": "acc_1",
                "passport_country": "KR",
                "traveler_identity_confirmed": True,
            },
            "price": {"amount": 100000, "currency": "KRW"},
            "cancellation_policy_acknowledged": True,
        },
    )

    assert response.status_code == 400
    assert "Approval" in response.json()["detail"]


def test_approval_payload_hash_mismatch_blocks_booking(
    client: TestClient, base_trip_payload: dict
) -> None:
    trip_id = create_ready_trip(client, base_trip_payload)
    approval_payload = {
        "hotel_option_id": "acc_1",
        "passport_country": "KR",
        "traveler_identity_confirmed": True,
    }
    approval = client.post(
        f"/trips/{trip_id}/approvals",
        json={
            "action_type": "booking",
            "summary": "Approve mock hotel booking",
            "payload": approval_payload,
            "price_ceiling": {"amount": 200000, "currency": "KRW"},
        },
    ).json()
    client.post(f"/trips/{trip_id}/approvals/{approval['approval_id']}/approve")

    response = client.post(
        f"/trips/{trip_id}/bookings/simulate",
        json={
            "action_type": "booking",
            "approval_id": approval["approval_id"],
            "payload": {
                "hotel_option_id": "acc_2",
                "passport_country": "KR",
                "traveler_identity_confirmed": True,
            },
            "price": {"amount": 150000, "currency": "KRW"},
            "cancellation_policy_acknowledged": True,
        },
    )

    assert response.status_code == 400
    assert "hash" in response.json()["detail"]


def test_simulated_booking_after_valid_approval(
    client: TestClient, base_trip_payload: dict
) -> None:
    trip_id = create_ready_trip(client, base_trip_payload)
    payload = {
        "hotel_option_id": "acc_1",
        "passport_country": "KR",
        "traveler_identity_confirmed": True,
    }
    approval = client.post(
        f"/trips/{trip_id}/approvals",
        json={
            "action_type": "booking",
            "summary": "Approve mock hotel booking",
            "payload": payload,
            "price_ceiling": {"amount": 200000, "currency": "KRW"},
        },
    ).json()
    client.post(f"/trips/{trip_id}/approvals/{approval['approval_id']}/approve")

    response = client.post(
        f"/trips/{trip_id}/bookings/simulate",
        json={
            "action_type": "booking",
            "approval_id": approval["approval_id"],
            "payload": payload,
            "price": {"amount": 150000, "currency": "KRW"},
            "cancellation_policy_acknowledged": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["simulated"] is True
    assert response.json()["status"] == "simulated_confirmed"


def test_cross_trip_approval_cannot_be_approved(
    client: TestClient, base_trip_payload: dict
) -> None:
    trip_id = create_ready_trip(client, base_trip_payload)
    other_trip_id = create_ready_trip(client, base_trip_payload)
    approval = client.post(
        f"/trips/{trip_id}/approvals",
        json={
            "action_type": "booking",
            "summary": "Approve mock hotel booking",
            "payload": {"hotel_option_id": "acc_1"},
            "price_ceiling": {"amount": 200000, "currency": "KRW"},
        },
    ).json()

    response = client.post(
        f"/trips/{other_trip_id}/approvals/{approval['approval_id']}/approve"
    )

    assert response.status_code == 400
    assert "trip" in response.json()["detail"]


def test_cross_trip_approval_cannot_be_rejected(
    client: TestClient, base_trip_payload: dict
) -> None:
    trip_id = create_ready_trip(client, base_trip_payload)
    other_trip_id = create_ready_trip(client, base_trip_payload)
    approval = client.post(
        f"/trips/{trip_id}/approvals",
        json={
            "action_type": "booking",
            "summary": "Approve mock hotel booking",
            "payload": {"hotel_option_id": "acc_1"},
            "price_ceiling": {"amount": 200000, "currency": "KRW"},
        },
    ).json()

    response = client.post(
        f"/trips/{other_trip_id}/approvals/{approval['approval_id']}/reject"
    )

    assert response.status_code == 400
    assert "trip" in response.json()["detail"]


def test_cross_trip_approval_cannot_simulate_booking(
    client: TestClient, base_trip_payload: dict
) -> None:
    trip_id = create_ready_trip(client, base_trip_payload)
    other_trip_id = create_ready_trip(client, base_trip_payload)
    payload = {
        "hotel_option_id": "acc_1",
        "passport_country": "KR",
        "traveler_identity_confirmed": True,
    }
    approval = client.post(
        f"/trips/{trip_id}/approvals",
        json={
            "action_type": "booking",
            "summary": "Approve mock hotel booking",
            "payload": payload,
            "price_ceiling": {"amount": 200000, "currency": "KRW"},
        },
    ).json()
    client.post(f"/trips/{trip_id}/approvals/{approval['approval_id']}/approve")

    response = client.post(
        f"/trips/{other_trip_id}/bookings/simulate",
        json={
            "action_type": "booking",
            "approval_id": approval["approval_id"],
            "payload": payload,
            "price": {"amount": 150000, "currency": "KRW"},
            "cancellation_policy_acknowledged": True,
        },
    )

    assert response.status_code == 400
    assert "trip" in response.json()["detail"]
