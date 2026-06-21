from __future__ import annotations

from fastapi.testclient import TestClient

from travel_agent.app.agent_core.cancellation import clear, is_cancelled, request_cancel
from travel_agent.app.db.session import get_session_factory
from travel_agent.app.schemas.agent import AgentRunCreateRequest, AgentRunStatus
from travel_agent.app.services.agent_service import AgentService


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


def test_continue_with_new_city_switches_destination(client: TestClient) -> None:
    created = client.post(
        "/agent/runs",
        json={
            "message": "삿포로 3박4일 여행 계획 짜줘",
            "locale": "ko-KR",
            "currency": "KRW",
            "timezone": "Asia/Seoul",
        },
    ).json()
    first = _detail(client, created["run_id"])
    assert "Sapporo" in (first["state"]["selected_destination"] or "")

    # 같은 대화에서 '도쿄'를 요청하면 삿포로가 아니라 도쿄로 전환되어야 한다.
    client.post(
        f"/agent/runs/{created['run_id']}/messages",
        json={"message": "도쿄 3박4일 계획 짜줘"},
    )
    second = _detail(client, created["run_id"])
    state = second["state"]
    assert "Tokyo" in (state["selected_destination"] or "")
    assert "Sapporo" not in (state["selected_destination"] or "")
    # 항공·숙소도 도쿄로 재검색되어 이전(삿포로) 결과가 남지 않는다.
    assert state["transport_options"]
    assert all("Tokyo" in opt["destination"] for opt in state["transport_options"])
    assert state["optimized_itinerary"]["days"]


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


def test_cancellation_registry_roundtrip() -> None:
    assert not is_cancelled("run_demo")
    request_cancel("run_demo")
    assert is_cancelled("run_demo")
    clear("run_demo")
    assert not is_cancelled("run_demo")
    # 빈 값은 항상 미취소로 본다.
    assert not is_cancelled(None)
    assert not is_cancelled("")


def test_run_stops_when_cancel_requested(client: TestClient, base_trip_payload: dict) -> None:
    # client fixture가 인메모리 DB를 구성한다 → 같은 DB에 서비스로 직접 붙어 begin/execute를
    # 분리 실행하고, 그 사이에 중지 신호를 넣어 협조적 취소를 검증한다.
    factory = get_session_factory()
    with factory() as session:
        service = AgentService(session)
        started = service.begin_run(AgentRunCreateRequest(**base_trip_payload))
        run_id = started.run_id
        request_cancel(run_id)  # 실행 전에 중지 → 첫 단계 경계에서 멈춘다
        try:
            service.execute_run(run_id)
            detail = service.get_run(run_id)
        finally:
            clear(run_id)
    assert detail.run.status == AgentRunStatus.cancelled
    # 중지됐으니 일정은 만들어지지 않는다(부분 결과만 남음).
    itinerary = detail.state.optimized_itinerary
    assert itinerary is None or not itinerary.days
    # 취소 처리 후 플래그는 비워진다.
    assert not is_cancelled(run_id)


def test_cancel_endpoint_is_safe_on_finished_run(
    client: TestClient, base_trip_payload: dict
) -> None:
    created = client.post("/agent/runs", json=base_trip_payload).json()
    run_id = created["run_id"]
    # 이미 완료된 run에 중지를 눌러도 안전(상태 유지, 200).
    response = client.post(f"/agent/runs/{run_id}/cancel")
    assert response.status_code == 200
    assert response.json()["run"]["status"] == "completed"


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


def test_update_itinerary_persists_user_edit(
    client: TestClient, base_trip_payload: dict
) -> None:
    created = client.post("/agent/runs", json=base_trip_payload).json()
    detail = _detail(client, created["run_id"])
    itinerary = detail["state"]["optimized_itinerary"]
    assert itinerary and itinerary["days"]
    before = len(itinerary["days"][0]["items"])
    assert before >= 1

    # 1일차 첫 관광 항목을 삭제해 저장(화면 편집 시뮬레이션).
    itinerary["days"][0]["items"] = itinerary["days"][0]["items"][1:]
    response = client.post(f"/agent/runs/{created['run_id']}/itinerary", json=itinerary)
    assert response.status_code == 200

    after = client.get(f"/agent/runs/{created['run_id']}").json()
    assert len(after["state"]["optimized_itinerary"]["days"][0]["items"]) == before - 1
