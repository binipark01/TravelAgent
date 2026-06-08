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
    options = [place_to_poi_option(place, destination, currency, kind=kind) for place in places]
    # 평점 높은 순으로 정렬해 좋은 곳부터 보여준다.
    options.sort(key=lambda option: option.rating or 0.0, reverse=True)
    return options[:limit]


def place_to_poi_option(
    place: dict[str, Any], destination: str, currency: str, *, kind: str = "restaurant"
) -> POIOption:
    rating = place.get("rating")
    category = place.get("category") or _KIND_DEFAULT_TYPE.get(kind, "맛집")
    notes = ["구글 지도 실시간 추출 · 방문 전 영업시간·예약 확인"]
    if rating:
        reviews = place.get("reviews")
        suffix = f" ({int(reviews):,} 리뷰)" if reviews else ""
        notes.insert(0, f"구글맵 평점 {rating}/5{suffix}")
    return POIOption(
        poi_id=new_id("poi"),
        title=place["name"],
        type=category,
        location=Location(name=destination, country=None, area=None),
        area=category,
        estimated_cost=Money(amount=0, currency=currency),
        rating=float(rating) if rating else None,
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
