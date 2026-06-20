from __future__ import annotations

import pytest

from travel_agent.app.llm import curator


@pytest.fixture(autouse=True)
def _clear_curator_cache() -> None:
    curator.clear_cache()


_FAKE_CITY = {
    "attractions": [
        {
            "name": "니혼다이라 유메테라스",
            "type": "전망대",
            "area": "니혼다이라",
            "why": "후지산·스루가만을 한 번에 보는 무료 전망지",
            "duration_min": 90,
            "rating": 4.3,
            "sources": ["https://nihondaira-yume-terrace.jp/"],
        }
    ],
    "restaurants": [
        {
            "name": "さわやか",
            "cuisine": "함박스테이크",
            "area": "시즈오카역",
            "why": "시즈오카 대표 로컬 체인",
            "rating": 4.3,
            "sources": ["https://www.genkotsu-hb.com/"],
        },
        {
            "name": "清水港みなみ",
            "cuisine": "마구로덮밥",
            "area": "시미즈",
            "why": "참치덮밥 가성비",
            "rating": 4.2,
            "sources": ["https://shimizuko-minami.owst.jp/"],
        },
    ],
}

_FAKE_NEARBY = {
    "hub": "시즈오카",
    "summary": "JR·버스로 닿는 근교 당일치기",
    "destinations": [
        {
            "name": "미호노마쓰바라",
            "travel_time": "JR+버스 약 45분",
            "transport": "JR 도카이도선",
            "highlights": ["후지산 조망", "소나무 해안"],
            "best_for": "반나절",
            "sources": ["https://www.visit-shizuoka.com/"],
        }
    ],
}


def test_curate_disabled_returns_none() -> None:
    # conftest의 autouse 픽스처가 ENABLE_LIVE_LLM=false → 큐레이터 비활성 → None.
    assert (
        curator.curate_city_pois(
            "시즈오카",
            interests=[],
            start_date=None,
            currency="KRW",
            attraction_pool=[],
            restaurant_pool=[],
        )
        is None
    )
    assert curator.curate_nearby("시즈오카") is None


def test_curate_city_pois_builds_pois_with_why_and_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(curator, "_enabled", lambda settings: True)
    monkeypatch.setattr(curator, "_run", lambda prompt, settings: _FAKE_CITY)

    result = curator.curate_city_pois(
        "시즈오카",
        interests=["맛집"],
        start_date=None,
        currency="KRW",
        attraction_pool=[],
        restaurant_pool=[],
    )
    assert result is not None
    assert len(result.attractions) == 1
    assert len(result.restaurants) == 2

    attraction = result.attractions[0]
    assert attraction.title == "니혼다이라 유메테라스"
    assert attraction.rating == 4.3
    assert attraction.metadata.source_ref.provider == "llm_curation"
    assert attraction.metadata.source_ref.source_url == "https://nihondaira-yume-terrace.jp/"
    # '왜 추천' + 출처가 notes에 실린다.
    assert any(note.startswith("💡") for note in attraction.notes)
    assert any("출처" in note for note in attraction.notes)

    # 식당이 한 종류가 아니라 다양하게 들어온다(함박·마구로).
    cuisines = {r.type for r in result.restaurants}
    assert cuisines == {"함박스테이크", "마구로덮밥"}


_FAKE_STAY = {
    "destination": "파리",
    "summary": "처음이면 1~7구 중심, 감성은 르마레",
    "areas": [
        {
            "name": "르마레(Le Marais)",
            "vibe": "감성 카페·편집숍 골목",
            "good_for": ["미술관 도보", "야경·디너"],
            "note": "치안 양호, 주말 혼잡",
            "source_url": "https://www.myrealtrip.com/",
        },
        {
            "name": "생제르맹데프레",
            "vibe": "고전적·차분한 좌안",
            "good_for": ["루브르·오르세 도보"],
            "note": None,
            "source_url": "https://www.myrealtrip.com/2",
        },
    ],
}


def test_curate_stay_areas_disabled_returns_none() -> None:
    assert curator.curate_stay_areas("파리") is None


def test_curate_stay_areas_builds_guide(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curator, "_enabled", lambda settings: True)
    monkeypatch.setattr(curator, "_run", lambda prompt, settings: _FAKE_STAY)

    guide = curator.curate_stay_areas("파리")
    assert guide is not None
    assert guide.destination == "파리"
    assert len(guide.areas) == 2
    first = guide.areas[0]
    assert first.name == "르마레(Le Marais)"
    assert "미술관 도보" in first.good_for
    assert first.note == "치안 양호, 주말 혼잡"
    assert first.source_url == "https://www.myrealtrip.com/"
    assert guide.metadata.source_ref.provider == "llm_curation"


def test_curate_nearby_builds_guide(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curator, "_enabled", lambda settings: True)
    monkeypatch.setattr(curator, "_run", lambda prompt, settings: _FAKE_NEARBY)

    guide = curator.curate_nearby("시즈오카")
    assert guide is not None
    assert guide.hub == "시즈오카"
    assert len(guide.destinations) == 1
    dest = guide.destinations[0]
    assert dest.name == "미호노마쓰바라"
    assert dest.travel_time == "JR+버스 약 45분"
    assert dest.source_url == "https://www.visit-shizuoka.com/"
    assert guide.metadata.source_ref.provider == "llm_curation"


def test_curate_city_caches_single_call(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_run(prompt: str, settings) -> dict:  # noqa: ANN001
        calls["n"] += 1
        return _FAKE_CITY

    monkeypatch.setattr(curator, "_enabled", lambda settings: True)
    monkeypatch.setattr(curator, "_run", fake_run)

    first = curator.curate_city_pois(
        "시즈오카", interests=["맛집"], start_date=None, currency="KRW",
        attraction_pool=[], restaurant_pool=[],
    )
    second = curator.curate_city_pois(
        "시즈오카", interests=["맛집"], start_date=None, currency="KRW",
        attraction_pool=[], restaurant_pool=[],
    )
    assert first is second
    assert calls["n"] == 1  # 같은 (목적지·관심사)는 캐시


def test_curate_city_empty_result_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curator, "_enabled", lambda settings: True)
    empty: dict = {"attractions": [], "restaurants": []}
    monkeypatch.setattr(curator, "_run", lambda prompt, settings: empty)
    assert (
        curator.curate_city_pois(
            "노웨어", interests=[], start_date=None, currency="KRW",
            attraction_pool=[], restaurant_pool=[],
        )
        is None
    )
