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
            "booking_required": True,
            "booking_url": "https://www.klook.com/ko/booking",
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
    # 예약 필요 + 예매 링크가 파싱된다.
    assert attraction.booking_required is True
    assert attraction.booking_url == "https://www.klook.com/ko/booking"
    assert any("예매" in note for note in attraction.notes)
    # 식당은 예약 필드 기본값(False/None).
    assert result.restaurants[0].booking_required is False

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


_FAKE_CHECKLIST = {
    "destination": "파리",
    "summary": "8월 파리는 더우니 가벼운 옷, 무비자라 여권만",
    "groups": [
        {"title": "전자·전압", "items": ["C/E타입 어댑터(230V)", "보조배터리"]},
        {"title": "서류", "items": ["여권(잔여 3개월+)", "유럽 무비자 90일"]},
    ],
}


def test_curate_checklist_disabled_returns_none() -> None:
    assert curator.curate_checklist("파리", context="파리, 8월") is None


def test_curate_checklist_builds_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curator, "_enabled", lambda settings: True)
    monkeypatch.setattr(curator, "run_codex_json", lambda *a, **k: _FAKE_CHECKLIST)

    checklist = curator.curate_checklist("파리", context="파리, 8월, 무비자")
    assert checklist is not None
    assert checklist.destination == "파리"
    assert len(checklist.groups) == 2
    assert checklist.groups[0].title == "전자·전압"
    assert "보조배터리" in checklist.groups[0].items
    assert checklist.metadata.source_ref.provider == "llm_curation"


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


_FAKE_LOCALTRANS = {
    "city": "런던",
    "summary": "히드로 익스프레스·지하철과 오이스터 카드 안내",
    "airport_transfers": [
        {
            "name": "히드로 익스프레스",
            "detail": "패딩턴역까지 직통",
            "price": "약 25파운드",
            "duration": "약 15분",
            "frequency": "15분 간격",
            "hours": "05:00~24:00",
            "sources": ["https://www.heathrowexpress.com/"],
        },
        {"name": "피카딜리 라인", "detail": "지하철로 시내 직결", "price": "약 5.5파운드"},
    ],
    "transit_passes": [
        {"name": "오이스터 카드", "detail": "지하철·버스 충전식", "price": "보증금 7파운드"},
    ],
    "tips": ["컨택리스 카드로도 오이스터 요금이 적용된다"],
}


def test_recommend_destinations_disabled_returns_none() -> None:
    # conftest autouse 픽스처가 ENABLE_LIVE_LLM=false → 비활성 → None.
    assert curator.recommend_destinations("일본 온천") is None


def test_recommend_destinations_parses_cities(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curator, "_enabled", lambda settings: True)
    monkeypatch.setattr(
        curator, "_run", lambda prompt, settings: {"cities": ["유후", "벳푸", "하코네", "구사쓰"]}
    )
    rec = curator.recommend_destinations("일본 온천 힐링", ["온천"], count=3)
    assert rec == ["유후", "벳푸", "하코네"]  # count로 잘림


def test_recommend_destinations_none_on_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curator, "_enabled", lambda settings: True)
    monkeypatch.setattr(curator, "_run", lambda prompt, settings: {"cities": []})
    assert curator.recommend_destinations("아무거나") is None


def test_run_retries_once_on_transient_none(monkeypatch: pytest.MonkeyPatch) -> None:
    # 첫 호출이 None(타임아웃·빈응답)이면 1회 재시도해 두 번째 결과를 쓴다.
    from travel_agent.app.config import get_settings

    calls = {"n": 0}

    def fake_codex(*args, **kwargs):
        calls["n"] += 1
        return None if calls["n"] == 1 else {"ok": True}

    monkeypatch.setattr(curator, "run_codex_json", fake_codex)
    assert curator._run("prompt", get_settings()) == {"ok": True}
    assert calls["n"] == 2


def test_run_gives_up_after_one_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    from travel_agent.app.config import get_settings

    calls = {"n": 0}

    def fake_codex(*args, **kwargs):
        calls["n"] += 1
        return None

    monkeypatch.setattr(curator, "run_codex_json", fake_codex)
    assert curator._run("prompt", get_settings()) is None
    assert calls["n"] == 2  # 최초 + 재시도 1회까지만


def test_curate_local_transport_disabled_returns_none() -> None:
    # conftest autouse 픽스처가 ENABLE_LIVE_LLM=false → 비활성 → None(정적 데이터로 폴백 안 됨).
    assert curator.curate_local_transport("런던", "영국") is None


def test_curate_local_transport_builds_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curator, "_enabled", lambda settings: True)
    monkeypatch.setattr(curator, "_run", lambda prompt, settings: _FAKE_LOCALTRANS)

    plan = curator.curate_local_transport("런던", "영국")
    assert plan is not None
    assert plan.city == "런던"
    assert len(plan.airport_transfers) == 2
    first = plan.airport_transfers[0]
    assert first.category == "airport"
    assert first.name == "히드로 익스프레스"
    assert first.frequency == "15분 간격"
    assert first.hours == "05:00~24:00"
    assert first.source_url == "https://www.heathrowexpress.com/"
    assert len(plan.transit_passes) == 1
    assert plan.transit_passes[0].category == "pass"
    assert plan.tips
    assert plan.metadata.source_ref.provider == "llm_curation"


def test_curate_local_transport_none_when_no_items(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curator, "_enabled", lambda settings: True)
    monkeypatch.setattr(curator, "_run", lambda prompt, settings: {"city": "X", "summary": "y"})
    assert curator.curate_local_transport("엑스시티") is None


_FAKE_MULTI = {
    "summary": "파리 3박 후 유로스타로 런던 2박",
    "segments": [
        {"city": "파리", "nights": 3, "highlights": ["루브르", "에펠탑"]},
        {"city": "런던", "nights": 2, "highlights": ["대영박물관"]},
    ],
    "legs": [
        {
            "origin": "파리",
            "destination": "런던",
            "mode": "기차(유로스타)",
            "duration": "약 2시간 20분",
            "booking_hint": "eurostar.com",
        }
    ],
    "tips": ["유로스타는 미리 예매가 저렴"],
}


def test_curate_multicity_disabled_or_single_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # LLM 꺼짐 → None.
    assert curator.curate_multicity(["파리", "런던"], total_days=5) is None
    # 활성이어도 목적지 1개면 None.
    monkeypatch.setattr(curator, "_enabled", lambda settings: True)
    assert curator.curate_multicity(["파리"], total_days=5) is None


def test_curate_multicity_builds_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curator, "_enabled", lambda settings: True)
    monkeypatch.setattr(curator, "_run", lambda prompt, settings: _FAKE_MULTI)

    plan = curator.curate_multicity(["파리", "런던"], total_days=5)
    assert plan is not None
    assert plan.destinations == ["파리", "런던"]
    assert [s.city for s in plan.segments] == ["파리", "런던"]
    assert plan.segments[0].nights == 3
    assert len(plan.legs) == 1
    assert plan.legs[0].mode == "기차(유로스타)"
    assert plan.legs[0].booking_hint == "eurostar.com"
    assert plan.metadata.source_ref.provider == "llm_curation"


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


# --- A1: 형식 일탈/방어 파싱 (누락 필드·잘못된 타입·non-dict 등에도 안 깨지는지) ---


def test_curate_city_drops_nameless_and_clamps_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curator, "_enabled", lambda settings: True)
    fake = {
        "attractions": [
            {"type": "전망대"},  # name 없음 → 버려진다
            "문자열-잘못된-항목",  # dict 아님 → 무시
            {
                "name": "거대명소",
                "duration_min": 9999,  # 상한 240으로 클램프
                "rating": 99,  # 범위 밖(0~5) → None
                "sources": ["https://example.com"],
            },
            {"name": "짧은곳", "duration_min": "x", "rating": "bad"},  # 타입 오류 → 기본/None
        ],
        "restaurants": [],
    }
    monkeypatch.setattr(curator, "_run", lambda prompt, settings: fake)
    result = curator.curate_city_pois(
        "도시", interests=[], start_date=None, currency="KRW",
        attraction_pool=[], restaurant_pool=[],
    )
    assert result is not None
    titles = [a.title for a in result.attractions]
    assert titles == ["거대명소", "짧은곳"]  # name 없는 항목·non-dict는 빠진다
    big = result.attractions[0]
    assert big.recommended_duration_minutes == 240  # 9999 클램프
    assert big.rating is None  # 범위 밖 별점은 버린다
    short = result.attractions[1]
    assert short.recommended_duration_minutes == 90  # 타입 오류 → 기본 90
    assert short.rating is None


def test_curate_nearby_non_dict_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curator, "_enabled", lambda settings: True)
    # destinations가 리스트가 아니거나 비면 None.
    monkeypatch.setattr(curator, "_run", lambda prompt, settings: {"destinations": "nope"})
    assert curator.curate_nearby("도시") is None
    monkeypatch.setattr(curator, "_run", lambda prompt, settings: None)
    assert curator.curate_nearby("도시2") is None


def test_curate_events_drops_sourceless(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import date as _date

    monkeypatch.setattr(curator, "_enabled", lambda settings: True)
    # 출처 URL 없는 행사는 버린다(없는 행사 지어내기 방지).
    fake = {
        "summary": "여름 축제",
        "events": [
            {"name": "출처있는축제", "category": "축제", "source_url": "https://x.example"},
            {"name": "출처없는행사", "category": "전시"},  # source_url 없음 → 버려짐
            {"category": "행사", "source_url": "https://y.example"},  # name 없음 → 버려짐
        ],
    }
    monkeypatch.setattr(curator, "_run", lambda prompt, settings: fake)
    guide = curator.curate_events("도시", _date(2026, 7, 1), _date(2026, 7, 5))
    assert guide is not None
    assert [e.name for e in guide.events] == ["출처있는축제"]


def test_curate_city_cache_key_includes_season_and_currency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A3: 시즌(월)·통화가 키에 들어가 서로 다른 달/통화는 캐시를 공유하지 않는다.
    from datetime import date as _date

    calls = {"n": 0}

    def fake_run(prompt: str, settings) -> dict:  # noqa: ANN001
        calls["n"] += 1
        return _FAKE_CITY

    monkeypatch.setattr(curator, "_enabled", lambda settings: True)
    monkeypatch.setattr(curator, "_run", fake_run)
    common = dict(interests=["맛집"], attraction_pool=[], restaurant_pool=[])
    curator.curate_city_pois("도시", start_date=_date(2026, 6, 1), currency="KRW", **common)
    curator.curate_city_pois("도시", start_date=_date(2026, 12, 1), currency="KRW", **common)
    curator.curate_city_pois("도시", start_date=_date(2026, 6, 1), currency="USD", **common)
    # 같은 (6월·KRW)만 캐시 적중 → 6월/KRW, 12월/KRW, 6월/USD = 3회 호출.
    assert calls["n"] == 3
