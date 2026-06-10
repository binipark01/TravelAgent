from __future__ import annotations

from travel_agent.app.connectors.accommodations.naver_hotel_browser import (
    _curate_hotels,
    build_hotel_query,
    hotel_to_option,
    parse_naver_hotel_text,
)


def _g_hotel(name: str, amount: int, *, provider: str = "naver_hotel", rating: float = 9.0):
    return hotel_to_option(
        {"name": name, "amount": amount, "rating": rating, "source_url": "https://x"},
        "Sapporo",
        3,
        "KRW",
        provider=provider,
    )


def _hotel(name: str, amount: int):
    return hotel_to_option(
        {"name": name, "amount": amount, "rating": 9.0, "source_url": "https://x"},
        "Sapporo",
        3,
        "KRW",
    )

SAMPLE = "\n".join(
    [
        "광고",
        "최대 75만원 적립",
        "인터컨티넨탈 삿포로 호텔 IHG",
        "9.55리뷰평점,일본",
        "371,672원~",
        "삿포로,일본",
        "9.03",
        "카리노 호텔 삿포로",
        "98,337원~",
        "삿포로,일본",
        "8.64",
    ]
)


def test_parse_pairs_name_price_rating() -> None:
    hotels = parse_naver_hotel_text(SAMPLE, source_url="https://x", limit=8)
    names = [h["name"] for h in hotels]

    assert "인터컨티넨탈 삿포로 호텔 IHG" in names
    inter = next(h for h in hotels if h["name"].startswith("인터컨티넨탈"))
    assert inter["amount"] == 371_672
    assert inter["rating"] == 9.55
    # 광고/적립 라인은 호텔 이름으로 잡히지 않는다.
    assert all("적립" not in name and "광고" not in name for name in names)


def test_hotel_to_option_is_real_not_mock() -> None:
    option = hotel_to_option(
        {"name": "카리노 호텔 삿포로", "amount": 98_337, "rating": 9.03, "source_url": "https://x"},
        "Sapporo",
        4,
        "KRW",
    )

    assert option.name == "카리노 호텔 삿포로"
    assert option.nightly_price.amount == 98_337
    assert option.total_price.amount == 98_337 * 4
    assert option.rating == round(9.03 / 2, 1)
    assert option.metadata.is_mock is False
    assert option.metadata.source_ref.is_live is True
    assert option.metadata.source_ref.provider == "naver_hotel"


def test_build_hotel_query_maps_city() -> None:
    assert build_hotel_query("Sapporo") == "삿포로 호텔"
    assert build_hotel_query("Osaka") == "오사카 호텔"
    # 국가 병기/새 도시도 처리한다.
    assert build_hotel_query("Bangkok, Thailand") == "방콕 호텔"
    assert build_hotel_query("다낭") == "다낭 호텔"


def test_stay_nights_uses_duration_and_caps_wide_range() -> None:
    from datetime import date

    from travel_agent.app.agents.accommodation import _stay_nights
    from travel_agent.app.schemas.brief import TripBrief

    # 기간 명시 → 그대로
    explicit = TripBrief(
        start_date=date(2026, 8, 1), end_date=date(2026, 8, 4), duration_nights=3, currency="KRW"
    )
    assert _stay_nights(explicit) == 3

    # 기간 미지정 + 범위가 한 달 → 기본 2박으로 제한(총액 폭주 방지)
    month = TripBrief(start_date=date(2026, 8, 1), end_date=date(2026, 8, 31), currency="KRW")
    assert _stay_nights(month) == 2


def test_nightly_budget_scales_with_travelers() -> None:
    from travel_agent.app.agents.accommodation import _nightly_budget
    from travel_agent.app.schemas.brief import TripBrief

    # 2명이 한 방, 1인 10만 → 방 1박 상한 20만
    two = TripBrief(travelers=2, budget_per_person=100_000, budget_total=200_000, currency="KRW")
    assert _nightly_budget(two) == 200_000

    # 1명, 1인 20만 → 20만
    one = TripBrief(travelers=1, budget_per_person=200_000, currency="KRW")
    assert _nightly_budget(one) == 200_000

    # 예산 정보 없음 → 상한 없음
    assert _nightly_budget(TripBrief(travelers=2, currency="KRW")) is None


def test_curate_hotels_filters_budget_and_sorts() -> None:
    options = [_hotel("A", 371_672), _hotel("B", 98_337), _hotel("C", 250_000), _hotel("D", 67_166)]

    curated = _curate_hotels(options, max_nightly_price=200_000, limit=8)

    # 20만원 초과(371,672 · 250,000)는 빠지고 가격 오름차순으로 정렬된다.
    assert [option.nightly_price.amount for option in curated] == [67_166, 98_337]
    assert any("최저가" in note for note in curated[0].notes)
    assert all(
        any("1박 20만원 이내" in note for note in option.notes) for option in curated
    )


def test_hotel_to_option_enriched_detail() -> None:
    google = hotel_to_option(
        {
            "name": "베셀호텔",
            "amount": 153_073,
            "rating": 4.5,
            "star": 4,
            "reviews": 2100,
            "amenities": ["무료 Wi-Fi", "온천", "주차"],
            "source_url": "https://g",
        },
        "Sapporo",
        2,
        "KRW",
        provider="google_hotel",
    )
    assert google.star_rating == 4
    assert google.review_count == 2100
    assert google.amenities == ["무료 Wi-Fi", "온천", "주차"]
    assert any("리뷰 2,100" in note for note in google.notes)

    # 네이버는 부가 정보가 없으면 비워 둔다.
    naver = hotel_to_option(
        {"name": "Y", "amount": 90_000, "rating": 9.0, "source_url": "u"},
        "Sapporo",
        2,
        "KRW",
        provider="naver_hotel",
    )
    assert naver.star_rating is None
    assert naver.amenities == []


def test_google_hotel_rating_not_halved() -> None:
    option = hotel_to_option(
        {"name": "Onsen Ryokan Yuen", "amount": 198_680, "rating": 4.3, "source_url": "https://g"},
        "Sapporo",
        3,
        "KRW",
        provider="google_hotel",
    )

    # 구글은 5점 만점이라 그대로(네이버처럼 절반으로 나누지 않는다).
    assert option.rating == 4.3
    assert option.metadata.source_ref.provider == "google_hotel"
    assert option.metadata.is_mock is False


def test_curate_hotels_includes_both_sources() -> None:
    naver = [
        _g_hotel("네이버호텔A", 90_000),
        _g_hotel("네이버호텔B", 100_000),
        _g_hotel("네이버호텔C", 110_000),
    ]
    google = [
        _g_hotel("구글호텔X", 120_000, provider="google_hotel", rating=4.0),
        _g_hotel("구글호텔Y", 130_000, provider="google_hotel", rating=4.0),
    ]

    curated = _curate_hotels(naver + google, max_nightly_price=None, limit=4)

    providers = {option.metadata.source_ref.provider for option in curated}
    # 네이버가 더 싸도 구글이 묻히지 않고 둘 다 노출된다.
    assert "naver_hotel" in providers
    assert "google_hotel" in providers


def test_hotel_constraint_filters() -> None:
    from travel_agent.app.connectors.accommodations.naver_hotel_browser import (
        _apply_hotel_filters,
        _min_rating,
        _min_star,
        _require_breakfast,
    )

    assert _min_star("4성급 이상 호텔 추천") == 4
    assert _min_rating("평점 4.5 이상으로") == 4.5
    assert _require_breakfast("조식 포함 호텔") is True
    assert _min_star("그냥 호텔") is None

    def gh(name, *, star=None, rating=4.0, amenities=None, provider="google_hotel"):
        raw = rating * 2 if provider == "naver_hotel" else rating
        return hotel_to_option(
            {"name": name, "amount": 100_000, "rating": raw, "star": star,
             "reviews": None, "amenities": amenities or [], "source_url": "x"},
            "Sapporo", 2, "KRW", provider=provider,
        )

    h4 = gh("g4", star=4)
    h3 = gh("g3", star=3)
    nav = gh("nav", provider="naver_hotel")  # 성급 정보 없음
    kept = _apply_hotel_filters([h3, h4, nav], 4, None, False)
    # 3성급은 빠지고, 4성급 + 성급 미상(네이버)은 남는다.
    assert h4 in kept
    assert nav in kept
    assert h3 not in kept


def test_curate_labels_unverified_constraint_matches() -> None:
    # 명시 조건(4성급+조식)을 걸었을 때, 데이터가 없어 '확인 불가'로 통과된 숙소엔
    # 충족된 것처럼 오해하지 않도록 라벨이 붙어야 한다.
    def gh(name, amount, *, provider, star=None, rating=4.6, amenities=None):
        raw = rating * 2 if provider == "naver_hotel" else rating
        return hotel_to_option(
            {"name": name, "amount": amount, "rating": raw, "star": star,
             "reviews": None, "amenities": amenities or [], "source_url": "x"},
            "Sapporo", 2, "KRW", provider=provider,
        )

    naver = gh("네이버호텔", 80_000, provider="naver_hotel")  # 성급 None, 편의시설 없음
    google = gh("구글호텔", 120_000, provider="google_hotel", star=4, amenities=["레스토랑"])

    curated = _curate_hotels(
        [naver, google], max_nightly_price=None, limit=8,
        min_star=4, require_breakfast=True,
    )
    nav = next(o for o in curated if o.name == "네이버호텔")
    goog = next(o for o in curated if o.name == "구글호텔")

    # 네이버: 성급·조식 정보가 없어 '미확인' 라벨이 붙는다.
    assert any("성급 미표기" in n for n in nav.notes)
    assert any("조식 여부 미확인" in n for n in nav.notes)
    # 구글: 4성급 + 레스토랑이라 라벨이 붙지 않는다.
    assert not any("성급 미표기" in n for n in goog.notes)
    assert not any("조식 여부 미확인" in n for n in goog.notes)


def test_infer_area_and_location_query() -> None:
    from travel_agent.app.connectors.accommodations.naver_hotel_browser import (
        _infer_area,
        _location_query,
    )

    assert _infer_area("그란벨 호텔 스스키노") == "스스키노"
    assert _infer_area("호텔 포르자 삿포로 스테이션") == "역 인근"
    assert _infer_area("더 놋 삿포로") is None
    assert _location_query("삿포로 스스키노 근처 호텔") == "스스키노"
    assert _location_query("역세권 호텔 찾아줘") == "역"
    assert _location_query("위치 좋은 호텔") == "중심"
    assert _location_query("그냥 호텔") is None


def test_curate_ranks_requested_area_first() -> None:
    def gh(name, amount, *, provider="naver_hotel", rating=8.6):
        return hotel_to_option(
            {"name": name, "amount": amount, "rating": rating, "source_url": "x"},
            "Sapporo", 2, "KRW", provider=provider,
        )

    far = gh("더 놋 삿포로", 70_000)  # 지역 없음, 더 쌈
    susukino = gh("그란벨 호텔 스스키노", 90_000)  # 스스키노, 더 비쌈

    curated = _curate_hotels(
        [far, susukino], max_nightly_price=None, limit=8, area_query="스스키노"
    )

    # 더 비싸도 요청 지역(스스키노)이 위로 오고, 지역 추론·칩이 붙는다.
    assert curated[0].name == "그란벨 호텔 스스키노"
    assert curated[0].location.area == "스스키노"
    assert any("📍 스스키노" in n for n in curated[0].notes)


def test_curate_ranks_verified_above_unverified() -> None:
    def mk(name, amount, *, provider, star=None, rating=4.5, amenities=None):
        raw = rating * 2 if provider == "naver_hotel" else rating
        return hotel_to_option(
            {"name": name, "amount": amount, "rating": raw, "star": star,
             "reviews": None, "amenities": amenities or [], "source_url": "x"},
            "Sapporo", 2, "KRW", provider=provider,
        )

    naver_unverified = mk("네이버 호텔", 80_000, provider="naver_hotel")  # 성급 None, 더 쌈
    google_verified = mk("구글 호텔", 120_000, provider="google_hotel", star=4)  # 4성급

    curated = _curate_hotels(
        [naver_unverified, google_verified], max_nightly_price=None, limit=8, min_star=4
    )

    # 더 비싸도 '확인된' 4성급이 위로 온다.
    assert curated[0].name == "구글 호텔"


def test_curate_hotels_dedupes_same_name_keeps_cheaper() -> None:
    naver = _g_hotel("베셀 호텔 캄파나", 126_000)
    google = _g_hotel("베셀호텔 캄파나", 121_000, provider="google_hotel", rating=4.5)

    curated = _curate_hotels([naver, google], max_nightly_price=None, limit=8)

    # 공백만 다른 같은 호텔 → 더 싼 쪽(구글 121,000)만 남는다.
    assert len(curated) == 1
    assert curated[0].nightly_price.amount == 121_000


def test_curate_hotels_over_budget_fallback() -> None:
    options = [_hotel("A", 371_672), _hotel("B", 300_000)]

    curated = _curate_hotels(options, max_nightly_price=200_000, limit=8)

    # 예산 이내 숙소가 없으면 전체에서 저렴한 순으로 보여주고 경고 태그를 단다.
    assert [option.nightly_price.amount for option in curated] == [300_000, 371_672]
    assert any("이내 숙소가 없어" in note for note in curated[0].notes)
