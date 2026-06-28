"""트리플 실코스 스토어 런타임 조회.

scripts/build_triple_store.py가 만든 도시별 컴팩트 JSON(.omo/triple-store/{도시}.json)을
지연 로드해 ① POI 좌표·평점(지도 정확도) ② 실제 day-by-day 코스(1순위 일정 소스)를 준다.
스토어 파일이 없으면 조용히 None을 반환해 기존 동작(웹검색)으로 폴백한다.
"""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path

# 스토어 위치: 기본은 리포 루트의 .omo/triple-store. 테스트는 env로 가리킨다.
_DEFAULT_DIR = Path(__file__).resolve().parents[4] / ".omo" / "triple-store"


def _store_dir() -> Path:
    override = os.environ.get("TRIPLE_STORE_DIR")
    return Path(override) if override else _DEFAULT_DIR


_CITY_CACHE: dict[str, dict | None] = {}
_LOCK = threading.Lock()

# 기간(일수) → 트리플 period 라벨. days = nights+1.
_PERIOD_BY_DAYS = {
    1: "당일치기", 2: "1박 2일", 3: "2박 3일", 4: "3박 4일", 5: "4박 5일", 6: "5박 6일",
}
_WHO_VALUES = {"혼자", "친구와", "연인과", "배우자와", "아이와", "부모님과", "기타"}
# 관심사 키워드 → 트리플 style(9종). 첫 매칭 우선, 없으면 기본값.
_STYLE_RULES: list[tuple[tuple[str, ...], str]] = [
    (("먹방", "맛집", "미식", "음식", "먹거리"), "관광보다 먹방"),
    (("쇼핑", "면세", "아울렛"), "쇼핑은 열정적으로"),
    (("힐링", "휴양", "온천", "여유", "휴식", "스파"), "여유롭게 힐링"),
    (("자연", "산", "바다", "해변", "공원", "트레킹", "하이킹"), "자연과 함께"),
    (("미술", "박물관", "역사", "문화", "예술", "전시", "유적"), "문화·예술·역사"),
    (("체험", "액티비티", "테마파크", "놀이"), "체험·액티비티"),
    (("sns", "인스타", "핫플", "감성", "포토"), "SNS 핫플레이스"),
]
_STYLE_DEFAULT = "유명 관광지는 필수"
_FATIGUE_TIGHT = "빼곡한 일정 선호"
_FATIGUE_LOOSE = "널널한 일정 선호"


@dataclass(frozen=True)
class PoiInfo:
    name: str
    lat: float | None
    lng: float | None
    rating: float | None
    category: str | None
    type: str | None  # attraction / restaurant / hotel


@dataclass(frozen=True)
class CourseStop:
    name: str
    type: str | None
    lat: float | None
    lng: float | None
    rating: float | None
    category: str | None


@dataclass(frozen=True)
class CourseResult:
    city: str
    label_key: str
    days: list[list[CourseStop]]


def _norm(name: str) -> str:
    s = re.sub(r"\(.*?\)", "", name or "")
    s = re.sub(r"[\s·,./\-—~]", "", s)
    return s.strip().lower()


def _load_city(city: str) -> dict | None:
    key = (city or "").strip()
    if not key:
        return None
    with _LOCK:
        if key in _CITY_CACHE:
            return _CITY_CACHE[key]
    path = _store_dir() / f"{key}.json"
    data: dict | None = None
    if path.exists():
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            data = None
    with _LOCK:
        _CITY_CACHE[key] = data
    return data


def clear_cache() -> None:
    with _LOCK:
        _CITY_CACHE.clear()


def has_city(city: str) -> bool:
    return _load_city(city) is not None


def _period_for_days(days: int) -> str | None:
    return _PERIOD_BY_DAYS.get(days)


def style_for_interests(interests: list[str] | None) -> str:
    text = " ".join(interests or []).lower()
    for keys, style in _STYLE_RULES:
        if any(k in text for k in keys):
            return style
    return _STYLE_DEFAULT


def fatigue_for_pace(pace: str | None) -> str:
    p = (pace or "").lower()
    if any(k in p for k in ("여유", "느긋", "널널", "relax", "slow", "힐링")):
        return _FATIGUE_LOOSE
    return _FATIGUE_TIGHT


def _who_value(who: str | None) -> str:
    w = (who or "").strip()
    return w if w in _WHO_VALUES else "혼자"


def lookup_poi(city: str, name: str) -> PoiInfo | None:
    """도시+POI명 → 좌표·평점·카테고리·타입. 정규화 정확매칭 후 부분일치 폴백. 없으면 None."""
    data = _load_city(city)
    if not data:
        return None
    pois: dict = data.get("pois") or {}
    norm = _norm(name)
    if not norm:
        return None
    row = pois.get(norm)
    if row is None:
        # 부분일치(우리 POI명이 '센소지·나카미세도리'면 트리플 '센소지'와 다름).
        for stored_norm, candidate in pois.items():
            if stored_norm and (stored_norm in norm or norm in stored_norm):
                row = candidate
                break
    if row is None:
        return None
    lat, lng, rating, category, ptype, original = (row + [None] * 6)[:6]
    return PoiInfo(
        name=original or name, lat=lat, lng=lng, rating=rating, category=category, type=ptype
    )


def lookup_course(
    city: str,
    days: int,
    *,
    interests: list[str] | None = None,
    who: str | None = None,
    pace: str | None = None,
) -> CourseResult | None:
    """도시·일수·관심사·동행·페이스에 가장 맞는 트리플 실코스를 ArrangedItinerary 변환용으로
    돌려준다. 범위 밖 도시·일수(7일+)·스토어 없음이면 None → 웹검색 폴백."""
    period = _period_for_days(days)
    if period is None:
        return None
    data = _load_city(city)
    if not data:
        return None
    courses: dict = data.get("courses") or {}
    who_v = _who_value(who)
    style = style_for_interests(interests)
    fatigue = fatigue_for_pace(pace)
    # 정확 키 → 완화(스타일 기본 → 피로도 토글 → 동행 혼자) 순으로 시도. 도시당 756키가 다 있어
    # 유효 값이면 정확 키가 거의 항상 적중한다.
    candidates = [
        f"{period}|{who_v}|{style}|{fatigue}",
        f"{period}|{who_v}|{_STYLE_DEFAULT}|{fatigue}",
        f"{period}|{who_v}|{style}|{_FATIGUE_TIGHT}",
        f"{period}|혼자|{_STYLE_DEFAULT}|{_FATIGUE_TIGHT}",
    ]
    raw_days = None
    label_key = ""
    for key in candidates:
        if key in courses:
            raw_days, label_key = courses[key], key
            break
    if not raw_days:
        return None
    out_days: list[list[CourseStop]] = []
    for day_names in raw_days:
        stops: list[CourseStop] = []
        for name in day_names:
            info = lookup_poi(city, name)
            stops.append(
                CourseStop(
                    name=name,
                    type=info.type if info else None,
                    lat=info.lat if info else None,
                    lng=info.lng if info else None,
                    rating=info.rating if info else None,
                    category=info.category if info else None,
                )
            )
        out_days.append(stops)
    return CourseResult(city=city, label_key=label_key, days=out_days)
