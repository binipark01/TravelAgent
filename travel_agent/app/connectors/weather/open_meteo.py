"""Open-Meteo 무료 날씨 API(키 불필요)로 여행 날짜의 날씨를 가져온다.

가까운 날짜는 실제 예보(forecast, ~16일), 먼 날짜는 작년 같은 날짜의 실측치
(historical archive)를 '예년 기준'으로 보여준다. 실패하면 빈 dict를 반환한다.
"""

from __future__ import annotations

import math
from datetime import date, time, timedelta
from urllib.parse import urlencode

from travel_agent.app.connectors.http_fetch import fetch_json

_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST = "https://api.open-meteo.com/v1/forecast"
_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
_TIMEOUT = 8


def _get(url: str, params: dict[str, str]) -> dict | None:
    # transient 실패는 1회 재시도(fetch_json). 실패하면 None → 호출부가 빈 dict로 폴백.
    return fetch_json(f"{url}?{urlencode(params)}", timeout=_TIMEOUT, retries=1)


def _openmeteo_geocode(name: str, language: str) -> tuple[float, float] | None:
    data = _get(_GEOCODE, {"name": name, "count": "1", "language": language, "format": "json"})
    results = (data or {}).get("results") or []
    if not results:
        return None
    first = results[0]
    return float(first["latitude"]), float(first["longitude"])


def geocode(place: str) -> tuple[float, float] | None:
    """도시명 → (위도, 경도). 한국어명을 먼저 Open-Meteo로 찾고, 거기에 없으면(암스테르담·
    비엔나처럼 한글 alt-name이 없는 도시) LLM 리졸버의 영문명·도심 좌표로 폴백한다.

    이 폴백 없이는 그런 도시에서 날씨·일몰(일정 일조 반영)·교통권 hub좌표(지도 클릭 bias)가
    조용히 비어버린다. LLM이 꺼져 있으면(오프라인) 폴백은 None이라 기존 동작과 같다.
    """
    city = place.split(",")[0].strip()
    coords = _openmeteo_geocode(city, "ko")
    if coords:
        return coords
    # 한글명이 Open-Meteo에 없을 때만 LLM 리졸버로 폴백(지연 import로 import 순환 회피).
    try:
        from travel_agent.app.llm.geo_resolver import resolve_place

        resolved = resolve_place(city)
    except Exception:  # noqa: BLE001 - 폴백이라 어떤 실패든 좌표 없음으로 처리
        resolved = None
    if resolved is None:
        return None
    if resolved.city_en:
        coords = _openmeteo_geocode(resolved.city_en, "en")
        if coords:
            return coords
    if resolved.lat is not None and resolved.lng is not None:
        return (resolved.lat, resolved.lng)
    return None


def _weather_label(code: int) -> str:
    if code == 0:
        return "☀️ 맑음"
    if code in (1, 2):
        return "🌤 대체로 맑음"
    if code == 3:
        return "☁️ 흐림"
    if code in (45, 48):
        return "🌫 안개"
    if 51 <= code <= 67:
        return "🌧 비"
    if 71 <= code <= 77:
        return "🌨 눈"
    if 80 <= code <= 82:
        return "🌦 소나기"
    if 85 <= code <= 86:
        return "🌨 눈"
    if 95 <= code <= 99:
        return "⛈ 뇌우"
    return "🌡 흐림"


def fetch_trip_weather(
    destination: str, start_date: date, end_date: date, *, today: date | None = None
) -> dict[date, str]:
    """여행 날짜별 날씨 라벨을 돌려준다. {date: '☀️ 맑음 22°/14°'}"""
    today = today or date.today()
    coords = geocode(destination)
    if coords is None or end_date < start_date:
        return {}
    lat, lon = coords

    near = (start_date - today).days <= 15 and end_date >= today
    if near:
        start = max(start_date, today)
        params = {
            "latitude": str(lat),
            "longitude": str(lon),
            "daily": "weathercode,temperature_2m_max,temperature_2m_min",
            "timezone": "auto",
            "start_date": start.isoformat(),
            "end_date": end_date.isoformat(),
        }
        data = _get(_FORECAST, params)
        year_shift = 0
        suffix = ""
    else:
        # 먼 미래는 예보가 없으므로 작년 같은 기간 실측치를 '예년 기준'으로 쓴다.
        try:
            start = start_date.replace(year=start_date.year - 1)
            end = end_date.replace(year=end_date.year - 1)
        except ValueError:
            return {}
        params = {
            "latitude": str(lat),
            "longitude": str(lon),
            "daily": "weathercode,temperature_2m_max,temperature_2m_min",
            "timezone": "auto",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }
        data = _get(_ARCHIVE, params)
        year_shift = 1
        suffix = " · 예년 기준"

    daily = (data or {}).get("daily") or {}
    times = daily.get("time") or []
    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []
    codes = daily.get("weathercode") or []
    result: dict[date, str] = {}
    for index, day_str in enumerate(times):
        try:
            day = date.fromisoformat(day_str).replace(
                year=date.fromisoformat(day_str).year + year_shift
            )
        except ValueError:
            continue
        if index >= len(tmax) or tmax[index] is None:
            continue
        label = _weather_label(int(codes[index]) if index < len(codes) else -1)
        high = round(tmax[index])
        low = round(tmin[index]) if index < len(tmin) and tmin[index] is not None else high
        result[day] = f"{label} {high}°/{low}°{suffix}"
    return result


# --- 일출·일몰 -------------------------------------------------------------------

# 표준 일출/일몰 천정각(굴절·태양 반지름 보정 포함). 도시 일출/일몰의 관용값.
_SUN_ZENITH_DEG = 90.833


def _local_sun_times(
    lat: float, lon: float, day: date, tz_offset_hours: float
) -> tuple[time, time]:
    """위/경도+날짜로 일출·일몰(현지시각)을 계산한다(외부 의존 없음, 어느 날짜든 동작).

    표준 일출/일몰 공식(NOAA 근사)을 쓴다. tz_offset_hours는 그 지역의 UTC offset(시간).
    백야/극야로 해가 안 뜨거나 안 지는 위도면 보수적으로 (06:00, 18:00)을 돌려준다.
    """
    n = day.timetuple().tm_yday
    lng_hour = lon / 15.0

    def _event(is_sunrise: bool) -> float | None:
        t = n + ((6 if is_sunrise else 18) - lng_hour) / 24.0
        mean_anom = 0.9856 * t - 3.289  # 태양 평균근점이각(deg)
        true_long = (
            mean_anom
            + 1.916 * math.sin(math.radians(mean_anom))
            + 0.020 * math.sin(math.radians(2 * mean_anom))
            + 282.634
        ) % 360
        right_asc = math.degrees(math.atan(0.91764 * math.tan(math.radians(true_long)))) % 360
        # 적경을 진황경과 같은 사분면으로 맞춘다.
        right_asc += (math.floor(true_long / 90) * 90) - (math.floor(right_asc / 90) * 90)
        right_asc /= 15.0  # → 시간
        sin_dec = 0.39782 * math.sin(math.radians(true_long))
        cos_dec = math.cos(math.asin(sin_dec))
        cos_h = (
            math.cos(math.radians(_SUN_ZENITH_DEG)) - sin_dec * math.sin(math.radians(lat))
        ) / (cos_dec * math.cos(math.radians(lat)))
        if cos_h > 1 or cos_h < -1:
            return None  # 백야/극야 — 그 이벤트가 없음
        h = (360 - math.degrees(math.acos(cos_h))) if is_sunrise else math.degrees(math.acos(cos_h))
        h /= 15.0
        local_mean_t = h + right_asc - 0.06571 * t - 6.622
        return (local_mean_t - lng_hour + tz_offset_hours) % 24.0

    def _to_time(hours: float | None, fallback: time) -> time:
        if hours is None:
            return fallback
        hours %= 24.0
        hh = int(hours)
        mm = int(round((hours - hh) * 60))
        if mm == 60:
            hh, mm = (hh + 1) % 24, 0
        return time(hh, mm)

    sunrise = _to_time(_event(is_sunrise=True), time(6, 0))
    sunset = _to_time(_event(is_sunrise=False), time(18, 0))
    return sunrise, sunset


def _parse_iso_time(value: str) -> time | None:
    """Open-Meteo의 'YYYY-MM-DDTHH:MM' 또는 시각 문자열에서 time만 뽑는다."""
    if not isinstance(value, str) or "T" not in value:
        return None
    try:
        return time.fromisoformat(value.split("T", 1)[1][:5])
    except ValueError:
        return None


def fetch_trip_daylight(
    destination: str, start_date: date, end_date: date, *, today: date | None = None
) -> dict[date, tuple[time, time]]:
    """여행 날짜별 (일출, 일몰) 현지시각을 돌려준다. {date: (sunrise, sunset)}.

    가까운 날짜는 Open-Meteo daily=sunrise,sunset(현지시각). 못 가져오거나 먼 날짜면
    위/경도+날짜로 로컬 계산해 폴백한다(어느 날짜든 동작, 외부 의존 없음). 지오코딩까지
    실패하면 빈 dict.
    """
    today = today or date.today()
    coords = geocode(destination)
    if coords is None or end_date < start_date:
        return {}
    lat, lon = coords

    result: dict[date, tuple[time, time]] = {}
    tz_offset_hours = lon / 15.0  # 폴백 계산용 경도 기반 추정 offset.

    near = (start_date - today).days <= 15 and end_date >= today
    if near:
        data = _get(
            _FORECAST,
            {
                "latitude": str(lat),
                "longitude": str(lon),
                "daily": "sunrise,sunset",
                "timezone": "auto",
                "start_date": max(start_date, today).isoformat(),
                "end_date": end_date.isoformat(),
            },
        )
        if isinstance(data, dict):
            offset = data.get("utc_offset_seconds")
            if isinstance(offset, int | float):
                tz_offset_hours = offset / 3600.0
            daily = data.get("daily") or {}
            times = daily.get("time") or []
            sunrises = daily.get("sunrise") or []
            sunsets = daily.get("sunset") or []
            for index, day_str in enumerate(times):
                try:
                    day = date.fromisoformat(day_str)
                except ValueError:
                    continue
                sr = _parse_iso_time(sunrises[index]) if index < len(sunrises) else None
                ss = _parse_iso_time(sunsets[index]) if index < len(sunsets) else None
                if sr and ss:
                    result[day] = (sr, ss)

    # 빠진 날짜(먼 미래·API 미반환)는 로컬 계산으로 채운다 — 어느 날짜든 정확.
    day = start_date
    while day <= end_date:
        if day not in result:
            result[day] = _local_sun_times(lat, lon, day, tz_offset_hours)
        day += timedelta(days=1)
    return result
