from __future__ import annotations

from travel_agent.app.llm import source_guide
from travel_agent.app.llm.source_guide import hints_for, source_hints_block


def test_known_regions_map_to_authoritative_sources() -> None:
    # 카탈로그 도시는 LLM 없이 국가로 해석되어 지역 권위 출처가 매핑된다.
    assert "TheFork" in hints_for("파리").restaurant  # 유럽(셰겐)
    assert "Tabelog" in hints_for("도쿄").restaurant
    assert "Wongnai" in hints_for("방콕").restaurant
    assert "Eater" in hints_for("뉴욕").restaurant
    assert "OpenRice" in hints_for("홍콩").restaurant


def test_unlisted_country_falls_back_to_generic() -> None:
    # 카탈로그·LLM 모두 못 잡으면 generic 폴백(맛집 리뷰 일반 안내).
    generic = source_guide._GENERIC
    assert hints_for("이스탄불") == generic
    assert hints_for("") == generic


def test_source_hints_block_lists_regional_sources() -> None:
    block = source_hints_block("파리")
    assert "맛집 리뷰" in block
    assert "TheFork" in block
    assert "GetYourGuide" in block  # 유럽 액티비티
    assert "유랑" in block  # 한국 유럽여행 커뮤니티
