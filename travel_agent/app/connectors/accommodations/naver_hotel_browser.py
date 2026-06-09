"""네이버 검색의 호텔 모듈을 브라우저로 분석해 실제 AccommodationOption을 만든다.

`naver_hotel_text.mjs`(Playwright)로 "<도시> 호텔" 검색 결과를 렌더링한 뒤,
호텔명·실시간 가격·평점을 파싱한다. 추출이 실패하면 빈 목록을 반환한다(mock 미사용).
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from travel_agent.app.schemas.common import Location, Money, SourceRef
from travel_agent.app.schemas.providers import AccommodationOption, ProviderMetadata
from travel_agent.app.utils.ids import new_id
from travel_agent.app.utils.time import expires_in, utc_now

_PRICE = re.compile(r"^\d{1,3}(?:,\d{3})*원~$")
_RATING = re.compile(r"^(\d\.\d{1,2})")
_LOC = re.compile(
    r"\s*[,，]\s*(일본|삿포로|도쿄|오사카|후쿠오카|교토|Japan|Sapporo|Tokyo|Osaka|Fukuoka).*$"
)
_HOTEL_KW = (
    "호텔", "리조트", "료칸", "게스트", "호스텔", "레지던스", "스테이",
    "Hotel", "Inn", "Resort", "Hostel",
)
_NOISE = (
    "적립", "할인", "쿠폰", "광고", "네이버", "최대", "만원", "보기", "선택",
    "지도", "필터", "정렬", "예약", "리뷰평점",
)
# 영문 도시명 -> 한글(검색 품질 향상). 키는 소문자.
_CITY_KO = {
    "sapporo": "삿포로", "tokyo": "도쿄", "osaka": "오사카", "fukuoka": "후쿠오카",
    "kyoto": "교토", "nagoya": "나고야", "okinawa": "오키나와", "naha": "오키나와",
    "taipei": "타이베이", "hong kong": "홍콩", "hongkong": "홍콩", "macau": "마카오",
    "shanghai": "상하이", "beijing": "베이징", "qingdao": "칭다오",
    "bangkok": "방콕", "phuket": "푸켓", "danang": "다낭", "da nang": "다낭",
    "hanoi": "하노이", "ho chi minh": "호치민", "singapore": "싱가포르",
    "kuala lumpur": "쿠알라룸푸르", "kota kinabalu": "코타키나발루", "cebu": "세부",
    "manila": "마닐라", "bali": "발리", "denpasar": "발리", "guam": "괌", "saipan": "사이판",
    "jeju": "제주", "busan": "부산", "japan": "일본",
}


class NaverHotelExtractionError(RuntimeError):
    pass


def build_hotel_query(destination: str) -> str:
    # "Bangkok, Thailand"처럼 국가 병기가 와도 도시명만 사용한다.
    city = destination.split(",")[0].strip()
    return f"{_CITY_KO.get(city.lower(), city)} 호텔"


def _is_hotel_name(line: str) -> bool:
    if _PRICE.match(line) or _RATING.match(line):
        return False
    if line.endswith("일본") and not any(keyword in line for keyword in _HOTEL_KW):
        return False
    if any(noise in line for noise in _NOISE):
        return False
    return any(keyword in line for keyword in _HOTEL_KW) or len(line) >= 5


def parse_naver_hotel_text(text: str, *, source_url: str, limit: int) -> list[dict[str, Any]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, line in enumerate(lines):
        if not _PRICE.match(line):
            continue
        amount = int(re.sub(r"[^\d]", "", line))
        name: str | None = None
        rating: float | None = None
        for back in range(index - 1, max(-1, index - 4), -1):
            candidate = lines[back]
            if _PRICE.match(candidate):
                break
            match = _RATING.match(candidate)
            if match and rating is None:
                rating = float(match.group(1))
            if name is None and _is_hotel_name(candidate):
                name = _LOC.sub("", candidate).strip()
        if name and name not in seen:
            seen.add(name)
            results.append(
                {"name": name, "amount": amount, "rating": rating, "source_url": source_url}
            )
            if len(results) >= limit:
                break
    return results


@dataclass(frozen=True, slots=True)
class NaverHotelBrowserExtractor:
    timeout_seconds: int = 35

    def extract(self, destination: str, *, limit: int = 8) -> list[dict[str, Any]]:
        script_path = Path(__file__).with_name("naver_hotel_text.mjs")
        url = f"https://search.naver.com/search.naver?query={quote_plus(build_hotel_query(destination))}"
        command = ["node", str(script_path), url, str(self.timeout_seconds)]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                encoding="utf-8",
                text=True,
                timeout=self.timeout_seconds + 8,
            )
        except FileNotFoundError as exc:
            raise NaverHotelExtractionError("node 실행 파일을 찾지 못했습니다.") from exc
        except subprocess.TimeoutExpired as exc:
            raise NaverHotelExtractionError("네이버 호텔 화면 추출 시간이 초과되었습니다.") from exc
        if completed.returncode != 0:
            raise NaverHotelExtractionError(
                completed.stderr.strip() or "네이버 호텔 화면 추출에 실패했습니다."
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise NaverHotelExtractionError(
                "네이버 호텔 화면 출력 형식이 올바르지 않습니다."
            ) from exc
        return parse_naver_hotel_text(
            payload.get("text", ""),
            source_url=payload.get("final_url") or url,
            limit=limit,
        )


def _min_star(text: str | None) -> int | None:
    match = re.search(r"(\d)\s*성급", text or "")
    return int(match.group(1)) if match else None


def _min_rating(text: str | None) -> float | None:
    match = re.search(r"평점\s*(\d(?:\.\d)?)\s*(?:이상|넘|초과|\+)", text or "")
    return float(match.group(1)) if match else None


def _require_breakfast(text: str | None) -> bool:
    return "조식" in (text or "")


def extract_live_accommodation_options(
    destination: str,
    *,
    nights: int,
    currency: str,
    timeout_seconds: int = 35,
    limit: int = 8,
    max_nightly_price: int | None = None,
    room_preference: str | None = None,
    request_text: str | None = None,
) -> list[AccommodationOption]:
    """네이버+구글 호텔 검색을 합쳐 실제 숙소만 추려서 정리한다(mock 미사용).

    브라우저 콜드스타트를 줄이려 두 소스를 순차로(한 번에 한 Chrome) 호출한다.
    room_preference(트윈/더블 등)가 있으면 상위 후보를 호텔별로 딥체크해 객실 유무를
    확인·표시한다.
    """
    options: list[AccommodationOption] = []

    # 네이버 호텔
    try:
        for hotel in NaverHotelBrowserExtractor(timeout_seconds=timeout_seconds).extract(
            destination, limit=max(limit, 12)
        ):
            options.append(
                hotel_to_option(hotel, destination, nights, currency, provider="naver_hotel")
            )
    except NaverHotelExtractionError:
        pass

    # 구글 호텔 (순환 import 방지를 위해 지연 import)
    try:
        from travel_agent.app.connectors.accommodations.google_hotel_browser import (
            GoogleHotelBrowserExtractor,
            GoogleHotelExtractionError,
        )

        for hotel in GoogleHotelBrowserExtractor(timeout_seconds=timeout_seconds).extract(
            destination, limit=max(limit, 12)
        ):
            options.append(
                hotel_to_option(hotel, destination, nights, currency, provider="google_hotel")
            )
    except GoogleHotelExtractionError:
        pass

    curated = _curate_hotels(
        options,
        max_nightly_price=max_nightly_price,
        limit=limit,
        min_star=_min_star(request_text),
        min_rating=_min_rating(request_text),
        require_breakfast=_require_breakfast(request_text),
    )

    # 침대 선호(트윈/더블)가 있으면 상위 후보를 호텔별로 딥체크해 객실 유무를 표시한다.
    if room_preference:
        try:
            from travel_agent.app.connectors.accommodations.google_hotel_browser import (
                annotate_room_availability,
            )

            curated = annotate_room_availability(
                curated, preference=room_preference, timeout_seconds=timeout_seconds
            )
        except (OSError, RuntimeError, ValueError):
            pass
    return curated


def _curate_hotels(
    options: list[AccommodationOption],
    *,
    max_nightly_price: int | None,
    limit: int,
    min_star: int | None = None,
    min_rating: float | None = None,
    require_breakfast: bool = False,
) -> list[AccommodationOption]:
    """예산(1박 상한)·성급·평점·조식·소스 다양성을 함께 보고 숙소를 추려서 정리한다.

    명시 조건(N성급 이상/평점 N 이상/조식)을 먼저 거른다. 정보가 없는 숙소는 확인 불가라
    제외하지 않고 남긴다. 같은 호텔이 두 소스에 모두 나오면 더 싼 쪽만 남기고, 예산 이내를
    우선한 뒤 네이버·구글이 둘 다 노출되도록 번갈아 담는다.
    """
    if not options:
        return []
    options = _dedupe_hotels(options)
    options = _apply_hotel_filters(options, min_star, min_rating, require_breakfast)
    options.sort(key=lambda option: option.nightly_price.amount or 10**12)

    over_budget_only = False
    if max_nightly_price:
        within = [
            option
            for option in options
            if (option.nightly_price.amount or 0) <= max_nightly_price
        ]
        if within:
            options = within
        else:
            over_budget_only = True

    # 소스(네이버·구글)별로 묶어 번갈아 담아 한쪽만 나오지 않게 한다.
    by_provider: dict[str, list[AccommodationOption]] = {}
    for option in options:
        by_provider.setdefault(option.metadata.source_ref.provider, []).append(option)
    provider_order = sorted(
        by_provider, key=lambda p: (p != "naver_hotel", p != "google_hotel", p)
    )
    ranked = [
        sorted(by_provider[p], key=lambda o: o.nightly_price.amount or 10**12)
        for p in provider_order
    ]
    curated = _round_robin_hotels(ranked, limit)
    curated.sort(key=lambda option: option.nightly_price.amount or 10**12)
    if not curated:
        return []

    cheapest = curated[0]
    cap_label = f"{max_nightly_price // 10000}만원" if max_nightly_price else None
    for option in curated:
        tags: list[str] = []
        if option is cheapest:
            tags.append("💰 최저가")
        if max_nightly_price and (option.nightly_price.amount or 0) <= max_nightly_price:
            tags.append(f"✅ 1박 {cap_label} 이내")
        if over_budget_only and option is cheapest:
            tags.append(f"⚠️ 1박 {cap_label} 이내 숙소가 없어 가장 저렴한 순")
        if tags:
            option.notes.insert(0, " · ".join(tags))
    return curated


def _has_breakfast(amenities: list[str]) -> bool:
    return any("조식" in item or "레스토랑" in item for item in amenities)


def _apply_hotel_filters(
    options: list[AccommodationOption],
    min_star: int | None,
    min_rating: float | None,
    require_breakfast: bool,
) -> list[AccommodationOption]:
    """명시 조건으로 거른다. 정보가 없는 숙소는 확인 불가라 남기고, 거른 결과가 비면 원복."""
    if min_star:
        kept = [o for o in options if o.star_rating is None or o.star_rating >= min_star]
        options = kept or options
    if min_rating:
        kept = [o for o in options if o.rating is None or o.rating >= min_rating]
        options = kept or options
    if require_breakfast:
        kept = [o for o in options if not o.amenities or _has_breakfast(o.amenities)]
        options = kept or options
    return options


def _dedupe_hotels(options: list[AccommodationOption]) -> list[AccommodationOption]:
    """이름이 같은(공백 무시) 숙소는 더 싼 것만 남긴다(소스 간 중복 제거)."""
    best: dict[str, AccommodationOption] = {}
    for option in sorted(options, key=lambda o: o.nightly_price.amount or 10**12):
        key = re.sub(r"\s+", "", option.name).lower()
        if key not in best:
            best[key] = option
    return list(best.values())


def _round_robin_hotels(
    lists: list[list[AccommodationOption]], limit: int
) -> list[AccommodationOption]:
    """여러 소스 리스트에서 번갈아 뽑아 limit개를 만든다(소스 다양성 보장)."""
    result: list[AccommodationOption] = []
    chosen_ids: set[int] = set()
    index = 0
    while len(result) < limit and any(index < len(items) for items in lists):
        for items in lists:
            if index < len(items):
                option = items[index]
                if id(option) not in chosen_ids:
                    chosen_ids.add(id(option))
                    result.append(option)
                    if len(result) >= limit:
                        break
        index += 1
    return result


_HOTEL_SOURCE_LABELS = {
    "naver_hotel": "네이버 호텔 검색",
    "google_hotel": "Google 호텔",
}


def hotel_to_option(
    hotel: dict[str, Any],
    destination: str,
    nights: int,
    currency: str,
    *,
    provider: str = "naver_hotel",
) -> AccommodationOption:
    nightly = int(hotel["amount"])
    raw_rating = hotel.get("rating")
    if not raw_rating:
        rating = None
    elif provider == "naver_hotel":
        rating = round(raw_rating / 2, 1)  # 네이버는 10점 만점 → 5점 만점
    else:
        rating = round(float(raw_rating), 1)  # 구글은 이미 5점 만점
    label = _HOTEL_SOURCE_LABELS.get(provider, _HOTEL_SOURCE_LABELS["naver_hotel"])
    notes = [f"{label} 실시간 추출 · 예약 전 가격/날짜 재확인 필요"]
    if raw_rating:
        scale = 10 if provider == "naver_hotel" else 5
        reviews = hotel.get("reviews")
        review_text = f", 리뷰 {int(reviews):,}" if reviews else ""
        notes.append(f"{label} 평점 {raw_rating}/{scale}{review_text}")
    star = hotel.get("star")
    amenities = [str(item) for item in (hotel.get("amenities") or []) if item]
    return AccommodationOption(
        option_id=new_id("acc"),
        name=hotel["name"],
        location=Location(name=destination, country=None, area=None),
        nightly_price=Money(amount=nightly, currency=currency),
        total_price=Money(amount=nightly * max(nights, 1), currency=currency),
        rating=rating,
        star_rating=int(star) if star else None,
        review_count=int(hotel["reviews"]) if hotel.get("reviews") else None,
        amenities=amenities,
        cancellation_policy=f"{label} 기준 표시가. 예약 사이트에서 취소 규정 확인 필요.",
        metadata=_live_metadata(hotel["source_url"], provider),
        notes=notes,
    )


def _live_metadata(source_url: str, provider: str = "naver_hotel") -> ProviderMetadata:
    now = utc_now()
    label = _HOTEL_SOURCE_LABELS.get(provider, _HOTEL_SOURCE_LABELS["naver_hotel"])
    source_ref = SourceRef(
        source_id=new_id("src"),
        provider=provider,
        source_url=source_url,
        title=f"{label} 실시간",
        reference=f"{provider}-{now.strftime('%Y%m%d%H%M%S')}",
        retrieved_at=now,
        expires_at=expires_in(1),
        is_live=True,
        is_mock=False,
        source_type="public_page",
        confidence=0.65,
        freshness_note=f"{label}에서 추출한 실시간 표시가. 예약 전 재확인 필요.",
    )
    return ProviderMetadata(
        provider_name=provider,
        retrieved_at=now,
        source_ref=source_ref,
        expires_at=expires_in(1),
        normalized_currency=None,
        is_mock=False,
    )
