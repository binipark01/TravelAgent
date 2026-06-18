from __future__ import annotations

from fastapi.testclient import TestClient

from travel_agent.app.config import Settings
from travel_agent.app.sources.registry import SourceRegistry


def test_provider_status_exposes_source_policy_without_secrets(client: TestClient) -> None:
    response = client.get("/providers/status")

    assert response.status_code == 200
    data = response.json()
    assert any(item["domain"] == "flights" and item["name"] == "mock" for item in data)
    assert any(
        item["domain"] == "flights" and item["name"] == "naver_flight" and item["enabled"] is False
        for item in data
    )
    assert all("API_KEY" not in str(item) for item in data)


def test_source_registry_allows_mock_only_when_fallback_or_dev() -> None:
    registry = SourceRegistry(Settings(enable_live_providers=False, provider_fallback_to_mock=True))
    enabled_flight_sources = registry.get_enabled_sources("flights")

    assert any(source.name == "mock" for source in enabled_flight_sources)
    assert not any(source.name == "naver_flight" for source in enabled_flight_sources)


def test_agent_runtime_persists_evidence_events_and_refs(
    client: TestClient, base_trip_payload: dict
) -> None:
    created = client.post("/agent/runs", json=base_trip_payload).json()

    response = client.post(
        f"/agent/runs/{created['run_id']}/messages",
        json={
            "message": (
                "출발지는 서울, 2026-10-03부터 2026-10-07까지, 여권 국적은 대한민국, 성인 2명"
            )
        },
    )
    assert response.status_code == 200

    # POST는 즉시 반환(running)하고 실행은 백그라운드에서 끝난다 → GET으로 최종 상태 확인.
    data = client.get(f"/agent/runs/{created['run_id']}").json()
    assert data["run"]["status"] == "completed"
    assert data["state"]["evidence_refs"]
    event_types = {event["type"] for event in data["events"]}
    assert "source_discovered" in event_types
    assert "source_rejected" in event_types
    assert "evidence_collected" in event_types
    assert "evidence_normalized" in event_types
    assert "evidence_ranked" in event_types
