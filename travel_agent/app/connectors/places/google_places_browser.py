"""구글 지도 식당 검색을 브라우저로 분석해 실제 POIOption을 만든다.

`google_places_extract.mjs`가 결과 카드에서 이름·평점·카테고리를 추출해 JSON으로
돌려준다. 추출이 실패하면 빈 목록을 반환한다(mock 미사용).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from travel_agent.app.schemas.common import Location, Money, SourceRef
from travel_agent.app.schemas.providers import POIOption, ProviderMetadata
from travel_agent.app.utils.ids import new_id
from travel_agent.app.utils.time import expires_in, utc_now


class GooglePlacesExtractionError(RuntimeError):
    pass


_KIND_QUERY = {
    "restaurant": "best restaurants in {city}",
    "attraction": "top tourist attractions in {city}",
}
_KIND_DEFAULT_TYPE = {"restaurant": "맛집", "attraction": "관광지"}

# 취향 키워드(한/영) -> 구글맵 검색어. 사용자가 명시하면 이걸 검색에 반영한다.
_CUISINE_INTEREST = {
    "스시": "sushi", "초밥": "sushi", "sushi": "sushi",
    "라멘": "ramen", "ramen": "ramen", "소바": "soba", "우동": "udon",
    "이자카야": "izakaya", "야키니쿠": "yakiniku bbq", "야끼니꾸": "yakiniku bbq",
    "스키야키": "sukiyaki", "샤브샤브": "shabu shabu", "텐푸라": "tempura",
    "튀김": "tempura", "돈카츠": "tonkatsu", "장어": "unagi eel",
    "해산물": "seafood", "회": "sashimi", "스테이크": "steak", "고기": "bbq",
    "카페": "cafe", "디저트": "dessert", "베이커리": "bakery",
    "오코노미야키": "okonomiyaki", "타코야키": "takoyaki",
    "한식": "korean restaurant", "중식": "chinese restaurant",
    "쌀국수": "pho", "딤섬": "dim sum", "마라": "mala hotpot",
}
_ATTRACTION_INTEREST = {
    "박물관": "museums", "미술관": "art museums", "공원": "parks",
    "쇼핑": "shopping", "온천": "onsen hot springs", "야경": "night view spots",
    "전망대": "observation decks", "신사": "shrines", "절": "temples",
    "사찰": "temples", "성": "castles", "수족관": "aquarium", "동물원": "zoo",
    "정원": "gardens", "시장": "markets", "테마파크": "theme parks",
}


def detect_interest(text: str | None, kind: str) -> str | None:
    """요청 문구에서 취향 키워드를 찾아 구글맵 검색어로 바꾼다(없으면 None)."""
    if not text:
        return None
    lowered = text.lower()
    table = _ATTRACTION_INTEREST if kind == "attraction" else _CUISINE_INTEREST
    for keyword, term in table.items():
        if keyword in lowered:
            return term
    return None


def build_maps_query(
    destination: str, kind: str = "restaurant", interest: str | None = None
) -> str:
    city = destination.split(",")[0].strip()
    if interest:
        return f"best {interest} in {city}"
    template = _KIND_QUERY.get(kind, _KIND_QUERY["restaurant"])
    return template.format(city=city)


def build_maps_url(destination: str, kind: str = "restaurant", interest: str | None = None) -> str:
    query = build_maps_query(destination, kind, interest)
    return f"https://www.google.com/maps/search/{quote_plus(query)}"


@dataclass(frozen=True, slots=True)
class GooglePlacesBrowserExtractor:
    timeout_seconds: int = 35

    def extract(
        self,
        destination: str,
        *,
        kind: str = "restaurant",
        interest: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        script_path = Path(__file__).with_name("google_places_extract.mjs")
        url = build_maps_url(destination, kind, interest)
        command = ["node", str(script_path), url, str(self.timeout_seconds), str(limit)]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                encoding="utf-8",
                text=True,
                timeout=self.timeout_seconds + 10,
            )
        except FileNotFoundError as exc:
            raise GooglePlacesExtractionError("node 실행 파일을 찾지 못했습니다.") from exc
        except subprocess.TimeoutExpired as exc:
            raise GooglePlacesExtractionError("구글 지도 추출 시간이 초과되었습니다.") from exc
        if completed.returncode != 0:
            raise GooglePlacesExtractionError(
                completed.stderr.strip() or "구글 지도 추출에 실패했습니다."
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise GooglePlacesExtractionError(
                "구글 지도 출력 형식이 올바르지 않습니다."
            ) from exc
        final_url = payload.get("final_url") or url
        results: list[dict[str, Any]] = []
        for place in payload.get("places", []):
            name = (place.get("name") or "").strip()
            if not name:
                continue
            results.append(
                {
                    "name": name,
                    "rating": place.get("rating"),
                    "reviews": place.get("reviews"),
                    "category": place.get("category"),
                    "source_url": final_url,
                }
            )
            if len(results) >= limit:
                break
        return results


def extract_live_pois(
    destination: str,
    *,
    currency: str,
    kind: str = "restaurant",
    interest: str | None = None,
    timeout_seconds: int = 35,
    limit: int = 8,
) -> list[POIOption]:
    try:
        places = GooglePlacesBrowserExtractor(timeout_seconds=timeout_seconds).extract(
            destination, kind=kind, interest=interest, limit=max(limit, 10)
        )
    except GooglePlacesExtractionError:
        return []
    # 식당은 평점만 보면 스시집만 몰린다 → 리뷰수 가중 점수 + 음식 종류 다양성으로 고른다.
    if kind == "restaurant":
        places = _curate_diverse_restaurants(places, limit)
    else:
        places = _rank_by_blended(places)[:limit]
    return [place_to_poi_option(place, destination, currency, kind=kind) for place in places]


def _review_count(place: dict[str, Any]) -> int:
    try:
        return int(place.get("reviews") or 0)
    except (TypeError, ValueError):
        return 0


def _blended_score(place: dict[str, Any], mean: float) -> float:
    """평점을 리뷰 수로 보정한 점수. 리뷰 적은 4.9 < 리뷰 많은 4.6 (베이지안 평균)."""
    try:
        rating = float(place.get("rating") or mean)
    except (TypeError, ValueError):
        rating = mean
    n = _review_count(place)
    confidence = 20.0
    return (rating * n + confidence * mean) / (n + confidence)


def _rank_by_blended(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rated = [p for p in places if p.get("rating")]
    mean = sum(float(p["rating"]) for p in rated) / len(rated) if rated else 4.3
    return sorted(places, key=lambda place: _blended_score(place, mean), reverse=True)


# 음식 종류 버킷 — 같은 종류는 최대 2곳까지만 넣어 다양성을 확보한다.
_CUISINE_BUCKETS: dict[str, tuple[str, ...]] = {
    "스시·해산물": (
        "스시", "초밥", "sushi", "회", "사시미", "해산물", "seafood", "오마카세", "kaiten",
    ),
    "라멘·면": ("라멘", "ramen", "소바", "우동", "면", "noodle", "쯔케멘"),
    "이자카야·술집": ("이자카야", "izakaya", "선술집", "술집", "bar", "펍", "pub"),
    "고기·구이": (
        "야키니쿠", "yakiniku", "bbq", "구이", "스테이크", "steak",
        "스키야키", "샤브", "곱창", "징기스칸",
    ),
    "튀김·돈카츠": ("돈카츠", "tonkatsu", "튀김", "텐푸라", "tempura", "카츠"),
    "카페·디저트": ("카페", "cafe", "디저트", "dessert", "베이커리", "bakery", "빵", "커피"),
    "양식": ("이탈리", "파스타", "피자", "pizza", "프렌치", "french", "양식", "버거", "비스트로"),
    "중식": ("중식", "중국", "chinese", "딤섬", "마라", "mala"),
    "한식": ("한식", "korean", "고깃집"),
    "일식 기타": ("오코노미야키", "타코야키", "카레", "규동", "텐동", "가정식", "japanese"),
}


def _cuisine_bucket(category: str | None) -> str:
    lowered = (category or "").lower()
    for bucket, keywords in _CUISINE_BUCKETS.items():
        if any(keyword.lower() in lowered for keyword in keywords):
            return bucket
    return category or "기타"


def _curate_diverse_restaurants(
    places: list[dict[str, Any]], limit: int, *, per_bucket_cap: int = 2
) -> list[dict[str, Any]]:
    ranked = _rank_by_blended(places)
    counts: dict[str, int] = {}
    picked: list[dict[str, Any]] = []
    leftover: list[dict[str, Any]] = []
    for place in ranked:
        bucket = _cuisine_bucket(place.get("category"))
        if counts.get(bucket, 0) < per_bucket_cap:
            counts[bucket] = counts.get(bucket, 0) + 1
            picked.append(place)
        else:
            leftover.append(place)
    result = picked[:limit]
    if len(result) < limit:
        result.extend(leftover[: limit - len(result)])
    return result[:limit]


def place_to_poi_option(
    place: dict[str, Any], destination: str, currency: str, *, kind: str = "restaurant"
) -> POIOption:
    rating = place.get("rating")
    review_count = _review_count(place) or None
    category = place.get("category") or _KIND_DEFAULT_TYPE.get(kind, "맛집")
    notes = ["구글 지도 실시간 추출 · 방문 전 영업시간·예약 확인"]
    if rating:
        suffix = f" ({review_count:,} 리뷰)" if review_count else ""
        notes.insert(0, f"구글맵 평점 {rating}/5{suffix}")
    return POIOption(
        poi_id=new_id("poi"),
        title=place["name"],
        type=category,
        location=Location(name=destination, country=None, area=None),
        area=category,
        estimated_cost=Money(amount=0, currency=currency),
        rating=float(rating) if rating else None,
        review_count=review_count,
        opening_hours=None,
        recommended_duration_minutes=90,
        booking_required=False,
        metadata=_live_metadata(place.get("source_url") or build_maps_url(destination)),
        notes=notes,
    )


def _live_metadata(source_url: str) -> ProviderMetadata:
    now = utc_now()
    source_ref = SourceRef(
        source_id=new_id("src"),
        provider="google_maps",
        source_url=source_url,
        title="Google 지도 맛집 검색 실시간",
        reference=f"google-maps-{now.strftime('%Y%m%d%H%M%S')}",
        retrieved_at=now,
        expires_at=expires_in(1),
        is_live=True,
        is_mock=False,
        source_type="public_page",
        confidence=0.6,
        freshness_note="구글 지도에서 추출한 실시간 맛집 정보. 영업시간/예약은 재확인 필요.",
    )
    return ProviderMetadata(
        provider_name="google_maps",
        retrieved_at=now,
        source_ref=source_ref,
        expires_at=expires_in(1),
        normalized_currency=None,
        is_mock=False,
    )
