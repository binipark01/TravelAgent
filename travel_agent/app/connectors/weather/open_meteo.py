"""Open-Meteo 무료 날씨 API(키 불필요)로 여행 날짜의 날씨를 가져온다.

가까운 날짜는 실제 예보(forecast, ~16일), 먼 날짜는 작년 같은 날짜의 실측치
(historical archive)를 '예년 기준'으로 보여준다. 실패하면 빈 dict를 반환한다.
"""

from __future__ import annotations

import json
from datetime import date
from urllib.parse import urlencode
from urllib.request import urlopen

_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST = "https://api.open-meteo.com/v1/forecast"
_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
_TIMEOUT = 8


def _get(url: str, params: dict[str, str]) -> dict | None:
    try:
        with urlopen(f"{url}?{urlencode(params)}", timeout=_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return None


def geocode(place: str) -> tuple[float, float] | None:
    city = place.split(",")[0].strip()
    data = _get(_GEOCODE, {"name": city, "count": "1", "language": "ko", "format": "json"})
    results = (data or {}).get("results") or []
    if not results:
        return None
    first = results[0]
    return float(first["latitude"]), float(first["longitude"])


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
