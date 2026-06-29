from __future__ import annotations

from datetime import date

from travel_agent.app.connectors.visa.entry_requirements import (
    lookup_entry_requirements,
    resolve_country,
)


def test_resolve_country_handles_city_and_aliases() -> None:
    assert resolve_country("Sapporo") == "일본"
    assert resolve_country("삿포로") == "일본"
    assert resolve_country("Tokyo, Japan") == "일본"
    assert resolve_country("다낭") == "베트남"
    assert resolve_country("Bali") == "인도네시아"
    assert resolve_country("Guam") == "괌"
    assert resolve_country("Unknownville") is None


def test_japan_is_visa_free_90() -> None:
    result = lookup_entry_requirements("Sapporo", "대한민국", date(2026, 7, 3), date(2026, 7, 7))
    assert result.destination_country == "일본"
    assert result.visa_required is False
    assert result.visa_free_days == 90
    assert "무비자" in result.summary
    assert result.requires_official_verification is True
    assert result.source_url
    assert result.metadata.is_mock is False


def test_indonesia_requires_voa() -> None:
    result = lookup_entry_requirements("Bali", "대한민국", date(2026, 7, 3), date(2026, 7, 7))
    assert result.destination_country == "인도네시아"
    assert result.visa_required is True
    assert "도착비자" in result.entry_authorization


def test_overstay_warning_when_trip_exceeds_visa_free_days() -> None:
    # 베트남 무비자 45일 < 50박 → 초과 경고
    result = lookup_entry_requirements("다낭", "대한민국", date(2026, 1, 1), date(2026, 2, 20))
    assert any("초과" in note for note in result.details)


def test_non_korean_passport_falls_back_to_official_check() -> None:
    result = lookup_entry_requirements("Tokyo", "United States", date(2026, 7, 3), date(2026, 7, 7))
    assert result.requires_official_verification is True
    assert result.visa_free_days is None  # 구조화 데이터를 단정하지 않는다


def test_missing_passport_is_flagged_for_unknown_destination() -> None:
    result = lookup_entry_requirements("Unknownville", None, None, None)
    assert "passport_country" in result.missing_required_info


def test_visa_agent_skips_domestic() -> None:
    # 국내(제주·부산)는 국제 입국 요건이 없어 비자 카드를 생략한다. 해외는 채운다.
    from travel_agent.app.agents.visa import VisaAgent
    from travel_agent.app.schemas.brief import TripBrief
    from travel_agent.app.schemas.trip import TripPlanState
    from travel_agent.app.utils.ids import new_id

    def visa_for(city: str):
        st = TripPlanState(trip_id=new_id("t"), currency="KRW", raw_user_message="x")
        st.selected_destination = city
        st.brief = TripBrief(
            selected_destination=city, destinations=[city], passport_country="한국"
        )
        VisaAgent().run(st)
        return st.visa_result

    assert visa_for("제주도") is None
    assert visa_for("부산") is None
    assert visa_for("도쿄") is not None
