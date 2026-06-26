"""워크플로 단계 실행 순서 골든(characterization) 테스트.

Supervisor 오케스트레이션을 리팩터할 때 '동작 보존'을 강제하는 안전망이다.
LLM off(conftest)라 결정적이므로, 요청 유형별로 기록되는 에이전트 step 순서가
정확히 아래와 같아야 한다. 순서·포함이 바뀌면 즉시 실패한다.

리팩터(예: supervisor 선언화) 전후로 이 순서가 한 단계도 달라지면 안 된다.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

FULL = [
    "IntakeAgent",
    "DestinationDiscoveryAgent",
    "FlightAgent",
    "AccommodationAgent",
    "RestaurantAgent",
    "RouteAgent",
    "BudgetAgent",
    "VisaAgent",
    "LocalTransportAgent",
    "FxAgent",
    "SafetyAgent",
    "NearbyAgent",
    "StayAreaAgent",
    "MultiCityAgent",
    "LocalEventsAgent",
    "ChecklistAgent",
    "TransportTicketsAgent",
    "PlanCriticAgent",
    "PresentationAgent",
]
FLIGHT_ONLY = [
    "IntakeAgent",
    "DestinationDiscoveryAgent",
    "FlightAgent",
    "PlanCriticAgent",
    "PresentationAgent",
]
ACCOM_ONLY = [
    "IntakeAgent",
    "DestinationDiscoveryAgent",
    "AccommodationAgent",
    "PlanCriticAgent",
    "PresentationAgent",
]


def _step_sequence(client: TestClient, message: str) -> list[str]:
    created = client.post(
        "/agent/runs",
        json={"message": message, "locale": "ko-KR", "currency": "KRW", "timezone": "Asia/Seoul"},
    ).json()
    data = client.get(f"/agent/runs/{created['run_id']}").json()
    assert data["run"]["status"] == "completed"
    return [step["agent_name"] for step in data["steps"]]


def test_full_plan_step_order(client: TestClient) -> None:
    seq = _step_sequence(
        client,
        "10월 초에 여자친구랑 4박 5일 일본 가고 싶어. 예산은 1인 120만원 정도. 맛집이랑 쇼핑 위주.",
    )
    assert seq == FULL


def test_flight_only_step_order(client: TestClient) -> None:
    assert _step_sequence(client, "도쿄 가는 항공권만 찾아줘") == FLIGHT_ONLY


def test_accommodation_only_step_order(client: TestClient) -> None:
    assert _step_sequence(client, "오사카 숙소만 추천해줘") == ACCOM_ONLY
