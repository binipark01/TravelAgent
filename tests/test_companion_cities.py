from __future__ import annotations

import pytest

from travel_agent.app.llm import curator
from travel_agent.app.llm.itinerary_arranger import _multicity_block


def test_companion_disabled_returns_empty() -> None:
    # conftest: ENABLE_LIVE_LLM=false → 웹검색 비활성 → 빈 리스트(단일 도시 유지).
    assert curator.curate_companion_cities("오사카", 4) == []


def test_companion_short_trip_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    # 3일 미만이면 본거지에 2일도 못 남겨 동반 도시를 붙이지 않는다.
    monkeypatch.setattr(curator, "_enabled", lambda settings: True)
    assert curator.curate_companion_cities("오사카", 2) == []


def test_companion_parses_and_drops_sourceless(monkeypatch: pytest.MonkeyPatch) -> None:
    curator.clear_cache()
    monkeypatch.setattr(curator, "_enabled", lambda settings: True)
    monkeypatch.setattr(
        curator,
        "_run",
        lambda prompt, settings: {
            "companions": [
                {
                    "city": "교토",
                    "days": 1,
                    "reason": "오사카에서 전철 15분, 사실상 필수",
                    "source_url": "https://example.com/kyoto",
                },
                # 출처 없는 추천 → 제외
                {"city": "고베", "days": 1, "reason": "야경"},
                # 본거지와 같은 도시 → 제외
                {"city": "오사카", "days": 1, "source_url": "https://x"},
            ]
        },
    )
    companions = curator.curate_companion_cities("오사카", 4)
    curator.clear_cache()

    cities = [c.city for c in companions]
    assert cities == ["교토"]
    assert companions[0].days == 1


def test_multicity_block_describes_city_split() -> None:
    block = _multicity_block("오사카", {"교토": 1})
    assert "교토 1일" in block
    assert "오사카" in block
    # 동반 도시 없으면 빈 문자열(기존 단일 도시 프롬프트 그대로).
    assert _multicity_block("오사카", None) == ""
    assert _multicity_block("오사카", {}) == ""
