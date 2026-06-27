from __future__ import annotations

from datetime import date, time

import pytest

from travel_agent.app.connectors.weather import open_meteo
from travel_agent.app.llm.geo_resolver import ResolvedPlace


def test_geocode_falls_back_to_english_name(monkeypatch: pytest.MonkeyPatch) -> None:
    # 한글명이 Open-Meteo에 없으면(암스테르담) LLM 리졸버의 영문명으로 다시 찾는다.
    calls: list[tuple[str, str]] = []

    def fake_om(name: str, language: str):
        calls.append((name, language))
        if name == "Amsterdam":
            return (52.374, 4.89)
        return None  # 한글 '암스테르담'은 못 찾음

    monkeypatch.setattr(open_meteo, "_openmeteo_geocode", fake_om)
    monkeypatch.setattr(
        "travel_agent.app.llm.geo_resolver.resolve_place",
        lambda name: ResolvedPlace(
            country_ko="네덜란드", iata="AMS", skyscanner="ams", hub_note=None,
            city_en="Amsterdam", lat=52.37, lng=4.90,
        ),
    )
    assert open_meteo.geocode("암스테르담") == (52.374, 4.89)
    assert ("암스테르담", "ko") in calls and ("Amsterdam", "en") in calls


def test_geocode_falls_back_to_resolver_coords(monkeypatch: pytest.MonkeyPatch) -> None:
    # 영문명으로도 Open-Meteo가 못 찾으면 리졸버가 준 도심 좌표를 그대로 쓴다.
    monkeypatch.setattr(open_meteo, "_openmeteo_geocode", lambda name, language: None)
    monkeypatch.setattr(
        "travel_agent.app.llm.geo_resolver.resolve_place",
        lambda name: ResolvedPlace(
            country_ko="X", iata=None, skyscanner=None, hub_note=None,
            city_en="Nowhereville", lat=12.34, lng=56.78,
        ),
    )
    assert open_meteo.geocode("아무데나") == (12.34, 56.78)


def test_geocode_none_when_resolver_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    # Open-Meteo도 못 찾고 리졸버도 None이면(오프라인 등) 기존처럼 None.
    monkeypatch.setattr(open_meteo, "_openmeteo_geocode", lambda name, language: None)
    monkeypatch.setattr(
        "travel_agent.app.llm.geo_resolver.resolve_place", lambda name: None
    )
    assert open_meteo.geocode("아무데나") is None


def test_local_sun_times_matches_known_values() -> None:
    # 도쿄(35.68N, 139.69E, +9): 하지/동지 일출·일몰이 실제 천문값과 분 단위로 맞아야 한다.
    sr, ss = open_meteo._local_sun_times(35.68, 139.69, date(2026, 6, 21), 9.0)
    assert time(4, 20) <= sr <= time(4, 35)  # 하지 일출 ~04:26
    assert time(18, 55) <= ss <= time(19, 5)  # 하지 일몰 ~19:00
    sr, ss = open_meteo._local_sun_times(35.68, 139.69, date(2026, 12, 21), 9.0)
    assert time(6, 40) <= sr <= time(6, 55)  # 동지 일출 ~06:47
    assert time(16, 25) <= ss <= time(16, 40)  # 동지 일몰 ~16:31


def test_local_sun_times_handles_polar_day() -> None:
    # 백야(레이캬비크 하지): 해가 거의 안 지므로 예외 없이 보수적 값을 돌려준다.
    sr, ss = open_meteo._local_sun_times(64.1, -21.9, date(2026, 6, 21), 0.0)
    assert isinstance(sr, time) and isinstance(ss, time)


def test_parse_iso_time() -> None:
    assert open_meteo._parse_iso_time("2026-07-03T04:26") == time(4, 26)
    assert open_meteo._parse_iso_time("2026-07-03T19:10") == time(19, 10)
    assert open_meteo._parse_iso_time("not-a-time") is None
    assert open_meteo._parse_iso_time(None) is None  # type: ignore[arg-type]


def test_fetch_trip_daylight_falls_back_to_local(monkeypatch) -> None:
    # 지오코딩은 되지만 API가 sunrise/sunset을 안 주면 로컬 계산으로 모든 날짜가 채워진다.
    monkeypatch.setattr(open_meteo, "geocode", lambda dest: (37.9, 139.0))
    monkeypatch.setattr(open_meteo, "_get", lambda url, params: None)  # API 실패
    out = open_meteo.fetch_trip_daylight(
        "니가타", date(2026, 7, 3), date(2026, 7, 5), today=date(2026, 7, 1)
    )
    # 3일 모두 (일출, 일몰)이 채워진다.
    assert set(out.keys()) == {date(2026, 7, 3), date(2026, 7, 4), date(2026, 7, 5)}
    for sr, ss in out.values():
        assert isinstance(sr, time) and isinstance(ss, time)
        assert sr < ss  # 일출이 일몰보다 이르다


def test_fetch_trip_daylight_no_geocode_returns_empty(monkeypatch) -> None:
    monkeypatch.setattr(open_meteo, "geocode", lambda dest: None)
    assert open_meteo.fetch_trip_daylight("Nowhere", date(2026, 7, 3), date(2026, 7, 5)) == {}
