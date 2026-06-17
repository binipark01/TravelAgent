"""네이버 검색의 호텔 모듈을 브라우저로 분석해 실제 AccommodationOption을 만든다.

`naver_hotel_text.mjs`(Playwright)로 "<도시> 호텔" 검색 결과를 렌더링한 뒤,
호텔명·실시간 가격·평점을 파싱한다. 추출이 실패하면 빈 목록을 반환한다(mock 미사용).
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import date
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


# 호텔에 좌표가 없어(네이버·구글 모두 미제공) 도보거리는 못 구한다. 대신 호텔명에서
# 지역/역을 추론해 위치 필터·표시에 쓴다. 도시별 핵심 지역(이름에 자주 포함됨).
_AREA_KEYWORDS = (
    # 삿포로
    "스스키노", "오도리", "타누키코지", "삿포로역", "나카지마공원", "마루야마", "신삿포로",
    # 도쿄
    "신주쿠", "시부야", "긴자", "우에노", "아사쿠사", "이케부쿠로", "시나가와", "롯폰기",
    # 오사카
    "난바", "우메다", "신사이바시", "도톤보리", "텐노지",
    # 교토/타이베이
    "기온", "교토역", "가와라마치", "시먼딩", "타이베이역",
)


def _infer_area(name: str) -> str | None:
    """호텔명에서 지역/역을 추론한다. 특정 지역명 우선, 없으면 '역 인근'."""
    for keyword in _AREA_KEYWORDS:
        if keyword in name:
            return keyword
    low = name.lower()
    if "스테이션" in name or "station" in low or name.rstrip().endswith("역"):
        return "역 인근"
    return None


def _location_query(text: str | None) -> str | None:
    """요청에서 원하는 위치를 뽑는다: 특정 지역명 / '역'(역세권) / '중심'(번화가) / None."""
    if not text:
        return None
    for keyword in _AREA_KEYWORDS:
        if keyword in text:
            return keyword
    if any(token in text for token in ("역 근처", "역세권", "역 가까", "스테이션", "station")):
        return "역"
    if any(token in text for token in ("위치 좋", "위치좋", "중심", "시내", "번화가")):
        return "중심"
    return None


def _area_matches(option: AccommodationOption, area_query: str) -> bool:
    area = option.location.area
    if area_query == "역":
        return bool(area and "역" in area)  # '삿포로역' · '역 인근'
    if area_query == "중심":
        return area is not None  # 인식되는 지역명이 이름에 있으면 중심가로 간주
    return area_query in option.name


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
    checkin: date | None = None,
    checkout: date | None = None,
) -> list[AccommodationOption]:
    """네이버+구글 호텔 검색을 합쳐 실제 숙소만 추려서 정리한다(mock 미사용).

    브라우저 콜드스타트를 줄이려 두 소스를 순차로(한 번에 한 Chrome) 호출한다.
    room_preference(트윈/더블 등)가 있으면 상위 후보를 호텔별로 딥체크해 객실 유무를
    확인·표시한다.
    """
    options: list[AccommodationOption] = []
    dated = checkin is not None and checkout is not None

    # 구글 호텔: 검색어에 날짜를 넣어 '그 날짜 기준 요금'을 받는다(성수기 등 반영). (지연 import)
    try:
        from travel_agent.app.connectors.accommodations.google_hotel_browser import (
            GoogleHotelBrowserExtractor,
            GoogleHotelExtractionError,
        )

        for hotel in GoogleHotelBrowserExtractor(timeout_seconds=timeout_seconds).extract(
            destination, limit=max(limit, 12), checkin=checkin, checkout=checkout
        ):
            options.append(
                hotel_to_option(hotel, destination, nights, currency, provider="google_hotel")
            )
    except GoogleHotelExtractionError:
        pass

    # 네이버 호텔: 날짜를 못 받는다(검색일 기준). 날짜 지정 검색에선 구글의 날짜 정확가와
    # 섞이면 싼 '오늘 가격'이 위로 올라와 오해를 부르므로, 날짜 미지정이거나 구글이 비었을
    # 때만(폴백) 사용한다.
    if not dated or not options:
        try:
            for hotel in NaverHotelBrowserExtractor(timeout_seconds=timeout_seconds).extract(
                destination, limit=max(limit, 12)
            ):
                options.append(
                    hotel_to_option(hotel, destination, nights, currency, provider="naver_hotel")
                )
        except NaverHotelExtractionError:
            pass

    curated = _curate_hotels(
        options,
        max_nightly_price=max_nightly_price,
        limit=limit,
        min_star=_min_star(request_text),
        min_rating=_min_rating(request_text),
        require_breakfast=_require_breakfast(request_text),
        area_query=_location_query(request_text),
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
    area_query: str | None = None,
) -> list[AccommodationOption]:
    """예산(1박 상한)·성급·평점·조식·위치·소스 다양성을 함께 보고 숙소를 추려서 정리한다.

    명시 조건(N성급 이상/평점 N 이상/조식)을 먼저 거른다. 정보가 없는 숙소는 확인 불가라
    제외하지 않고 남긴다. 위치 요청(area_query)이 있으면 해당 지역 숙소를, 명시 조건이
    있으면 '확인된' 숙소를 위로 올린다(제외하진 않음). 같은 호텔이 두 소스에 모두 나오면
    더 싼 쪽만 남기고, 네이버·구글이 둘 다 노출되도록 번갈아 담는다.
    """
    if not options:
        return []
    options = _dedupe_hotels(options)
    options = _apply_hotel_filters(options, min_star, min_rating, require_breakfast)
    # 좌표가 없어 도보거리는 못 구하니 호텔명에서 지역/역을 추론해 둔다(필터·표시용).
    for option in options:
        option.location.area = _infer_area(option.name)

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

    def _unverified(option: AccommodationOption) -> int:
        """명시 조건 대비 '확인 불가' 항목 수(작을수록 위)."""
        miss = 0
        if min_star and option.star_rating is None:
            miss += 1
        if min_rating and option.rating is None:
            miss += 1
        if require_breakfast and not _has_breakfast(option.amenities):
            miss += 1
        return miss

    def _rank(option: AccommodationOption) -> tuple[int, int, float]:
        # 위치 일치 > 조건 확인됨 > 저렴한 순.
        area_miss = 0 if (area_query and _area_matches(option, area_query)) else (
            1 if area_query else 0
        )
        return (area_miss, _unverified(option), option.nightly_price.amount or 10**12)

    area_hit = bool(area_query) and any(_area_matches(o, area_query) for o in options)

    # 소스(네이버·구글)별로 묶어 _rank 순으로 정렬한 뒤 번갈아 담아 한쪽만 나오지 않게 한다.
    by_provider: dict[str, list[AccommodationOption]] = {}
    for option in options:
        by_provider.setdefault(option.metadata.source_ref.provider, []).append(option)
    provider_order = sorted(
        by_provider, key=lambda p: (p != "naver_hotel", p != "google_hotel", p)
    )
    ranked = [sorted(by_provider[p], key=_rank) for p in provider_order]
    curated = _round_robin_hotels(ranked, limit)
    if not curated:
        return []
    cheapest = min(curated, key=lambda o: o.nightly_price.amount or 10**12)
    curated.sort(key=_rank)  # 표시 순서: 위치>확인>가격

    cap_label = f"{max_nightly_price // 10000}만원" if max_nightly_price else None
    for option in curated:
        tags: list[str] = []
        if option is cheapest:
            tags.append("💰 최저가")
        if option.location.area:
            tags.append(f"📍 {option.location.area}")
        if max_nightly_price and (option.nightly_price.amount or 0) <= max_nightly_price:
            tags.append(f"✅ 1박 {cap_label} 이내")
        if over_budget_only and option is cheapest:
            tags.append(f"⚠️ 1박 {cap_label} 이내 숙소가 없어 가장 저렴한 순")
        # 위치 요청 지역을 못 찾은 경우(가장 위 항목에만) 안내.
        specific_area = area_query not in (None, "역", "중심")
        if specific_area and not area_hit and option is curated[0]:
            tags.append(f"⚠️ '{area_query}' 인근 숙소를 찾지 못해 전체 표시")
        # 명시 조건을 걸었지만 그 숙소의 해당 정보가 없어 '확인 불가'로 통과시킨 경우,
        # 충족된 것처럼 오해하지 않도록 라벨을 단다(주로 네이버: 성급·편의시설 미제공).
        if min_star and option.star_rating is None:
            tags.append("ℹ️ 성급 미표기(확인 필요)")
        if min_rating and option.rating is None:
            tags.append("ℹ️ 평점 미표기(확인 필요)")
        if require_breakfast and not _has_breakfast(option.amenities):
            tags.append("ℹ️ 조식 여부 미확인")
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
