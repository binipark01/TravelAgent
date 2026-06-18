from __future__ import annotations

from fastapi.testclient import TestClient


def _detail(client: TestClient, run_id: str) -> dict:
    # POST는 run_id만 즉시 반환하고 실제 실행은 백그라운드로 끝난다.
    # (TestClient는 백그라운드 태스크를 동기적으로 끝내므로 곧바로 GET하면 완료 상태다.)
    response = client.get(f"/agent/runs/{run_id}")
    assert response.status_code == 200
    return response.json()


def test_natural_language_request_creates_agent_run(
    client: TestClient, base_trip_payload: dict
) -> None:
    created = client.post("/agent/runs", json=base_trip_payload).json()

    assert created["trip_id"].startswith("trip_")
    assert created["run_id"].startswith("run_")

    detail = _detail(client, created["run_id"])
    assert detail["run"]["status"] == "completed"
    # 후속 질문 없이 항상 완성: 누락 필드는 보고하지 않고 조용히 채운다.
    assert detail["state_summary"]["missing_fields"] == []
    assert detail["state"]["optimized_itinerary"]["days"]
    assert detail["state"]["evidence_refs"]
    assert any(event["type"] == "source_discovered" for event in detail["events"])
    assert any(event["type"] == "evidence_collected" for event in detail["events"])
    assert any(event["type"] == "run_completed" for event in detail["events"])


def test_agent_run_records_steps_and_events(client: TestClient, base_trip_payload: dict) -> None:
    created = client.post("/agent/runs", json=base_trip_payload).json()

    data = _detail(client, created["run_id"])
    assert data["run"]["status"] == "completed"
    agent_names = [step["agent_name"] for step in data["steps"]]
    assert "IntakeAgent" in agent_names
    assert "DestinationDiscoveryAgent" in agent_names
    assert "PresentationAgent" in agent_names
    assert all(step["status"] != "skipped" for step in data["steps"])
    assert any(event["type"] == "user_message" for event in data["events"])
    assert any(event["type"] == "source_discovered" for event in data["events"])


def test_follow_up_message_resumes_agent_run(client: TestClient, base_trip_payload: dict) -> None:
    created = client.post("/agent/runs", json=base_trip_payload).json()
    response = client.post(
        f"/agent/runs/{created['run_id']}/messages",
        json={"message": "출발지는 서울, 2026-10-03부터 2026-10-07까지, 여권 국적은 대한민국."},
    )
    assert response.status_code == 200

    data = _detail(client, created["run_id"])
    assert data["run"]["status"] == "completed"
    state = data["state"]
    assert state["brief"]["origin"] == "서울"
    assert state["brief"]["start_date"] == "2026-10-03"
    assert state["brief"]["end_date"] == "2026-10-07"
    assert state["brief"]["passport_country"] == "대한민국"
    assert state["transport_options"]
    assert state["accommodation_options"]
    assert state["optimized_itinerary"]["days"]
    assert state["budget"]["total_estimated_cost"] > 0
    assert state["critic_findings"]
    assert any(step["agent_name"] == "PresentationAgent" for step in data["steps"])
    assert any(event["type"] == "plan_ready" for event in data["events"])


def test_continue_completes_even_with_sparse_request(
    client: TestClient,
) -> None:
    created = client.post(
        "/agent/runs",
        json={
            "message": "그냥 해외 여행 가고 싶어.",
            "locale": "ko-KR",
            "currency": "KRW",
            "timezone": "Asia/Seoul",
        },
    ).json()
    response = client.post(f"/agent/runs/{created['run_id']}/continue")

    assert response.status_code == 200
    data = response.json()
    # 정보가 부족해도 대기하지 않고 기본값으로 채워 계획을 완성한다.
    assert data["run"]["status"] == "completed"
    assert data["state"]["missing_fields"] == []
    assert data["state"]["selected_destination"]
    assert data["state"]["optimized_itinerary"]["days"]


def test_flight_search_request_returns_transport_options(client: TestClient) -> None:
    message = (
        "삿포로 여행갈건데 기간은 7월 초 중순 사이고 "
        "오전출발 비행기 돌아오는건 오후출발 비행기 항공권 찾아줘"
    )
    created = client.post(
        "/agent/runs",
        json={
            "message": message,
            "locale": "ko-KR",
            "currency": "KRW",
            "timezone": "Asia/Seoul",
        },
    ).json()

    data = _detail(client, created["run_id"])
    assert data["run"]["status"] == "completed"
    state = data["state"]
    assert state["brief"]["origin"] == "서울"
    assert state["selected_destination"] == "Sapporo"
    assert state["missing_fields"] == []
    assert state["transport_options"]
    flight = state["transport_options"][0]
    assert flight["destination"] == "Sapporo"
    assert flight["departure_time"].startswith("2026-07-03T09:30")
    assert flight["return_departure_time"].startswith("2026-07-15T15:20")
    agent_names = [step["agent_name"] for step in data["steps"]]
    assert "FlightAgent" in agent_names
    assert "AccommodationAgent" not in agent_names
    assert state["optimized_itinerary"] is None


def test_accommodation_search_request_returns_accommodation_options(
    client: TestClient,
) -> None:
    message = "오사카 2026-10-03부터 2026-10-07까지 성인 2명 숙소 찾아줘. 호텔 위주."
    created = client.post(
        "/agent/runs",
        json={
            "message": message,
            "locale": "ko-KR",
            "currency": "KRW",
            "timezone": "Asia/Seoul",
        },
    ).json()

    data = _detail(client, created["run_id"])
    assert data["run"]["status"] == "completed"
    state = data["state"]
    assert state["selected_destination"] == "Osaka"
    assert state["missing_fields"] == []
    assert state["transport_options"] == []
    assert state["accommodation_options"]
    assert state["optimized_itinerary"] is None
    agent_names = [step["agent_name"] for step in data["steps"]]
    assert "FlightAgent" not in agent_names
    assert "AccommodationAgent" in agent_names
    assert "RestaurantAgent" not in agent_names
    assert "RouteAgent" not in agent_names
