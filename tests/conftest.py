from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from travel_agent.app.main import create_app


@pytest.fixture(autouse=True)
def _disable_live_llm() -> None:
    # 테스트는 결정론적 fallback 경로만 사용한다 (live LLM/Codex/브라우저 호출 금지).
    os.environ["ENABLE_LIVE_LLM"] = "false"
    os.environ["ENABLE_FLIGHT_SOURCE_PROBES"] = "false"


@pytest.fixture()
def client() -> TestClient:
    app = create_app("sqlite:///:memory:")
    return TestClient(app)


@pytest.fixture()
def base_trip_payload() -> dict:
    return {
        "message": (
            "10월 초에 여자친구랑 4박 5일 일본 가고 싶어. "
            "예산은 1인 120만원 정도. 맛집이랑 쇼핑 위주."
        ),
        "locale": "ko-KR",
        "currency": "KRW",
        "timezone": "Asia/Seoul",
    }


def create_ready_trip(client: TestClient, base_trip_payload: dict) -> str:
    response = client.post("/trips", json=base_trip_payload)
    assert response.status_code == 200
    trip_id = response.json()["trip_id"]
    response = client.post(
        f"/trips/{trip_id}/messages",
        json={"message": "출발지는 서울이고 10월 3일부터 7일까지 가능해. 여권 국적은 대한민국."},
    )
    assert response.status_code == 200
    return trip_id
