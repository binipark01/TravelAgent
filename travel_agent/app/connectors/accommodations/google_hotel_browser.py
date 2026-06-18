"""구글 호텔 검색 화면을 브라우저로 분석해 실제 숙소 후보를 만든다.

`google_hotel_extract.mjs`가 호텔 카드(aria-label)에서 이름·가격·평점을 구조적으로
추출해 JSON으로 돌려준다. 추출이 실패하면 빈 목록을 반환한다(mock 미사용).
"""

from __future__ import annotations

import json
import math
import re
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote_plus

from travel_agent.app.connectors.accommodations.naver_hotel_browser import build_hotel_query

if TYPE_CHECKING:
    from travel_agent.app.schemas.providers import AccommodationOption


class GoogleHotelExtractionError(RuntimeError):
    pass


def build_google_hotel_url(
    destination: str, checkin: date | None = None, checkout: date | None = None
) -> str:
    """구글 호텔 검색 URL. 날짜를 주면 쿼리 텍스트에 넣어 그 날짜 기준 요금을 받는다.

    구글 트래블은 checkin/checkout URL 파라미터를 무시하지만, 검색어에 자연어 날짜를
    넣으면 파싱해서 체크인/체크아웃을 그 날짜로 설정한다(예: '삿포로 호텔 2026년 7월
    7일 ~ 7월 11일' → 7/7~7/11 요금).
    """
    query = build_hotel_query(destination)
    if checkin and checkout and checkout > checkin:
        query = (
            f"{query} {checkin.year}년 {checkin.month}월 {checkin.day}일 "
            f"~ {checkout.month}월 {checkout.day}일"
        )
    return f"https://www.google.com/travel/search?q={quote_plus(query)}"


def build_hotel_booking_url(
    hotel_name: str, checkin: date | None = None, checkout: date | None = None
) -> str:
    """특정 호텔의 예약 링크. 날짜를 주면 쿼리 텍스트에 넣어 그 날짜로 열리게 한다.

    도시 전체 검색 결과(날짜 없음)가 아니라 '그 호텔 + 여행 날짜'로 열어서, 예약을
    누르면 오늘이 아니라 여행 체크인/체크아웃이 채워진 상태로 보이게 한다.
    """
    query = hotel_name
    if checkin and checkout and checkout > checkin:
        query = (
            f"{hotel_name} {checkin.year}년 {checkin.month}월 {checkin.day}일 "
            f"~ {checkout.month}월 {checkout.day}일"
        )
    return f"https://www.google.com/travel/search?q={quote_plus(query)}"


@dataclass(frozen=True, slots=True)
class GoogleHotelBrowserExtractor:
    timeout_seconds: int = 35

    def extract(
        self,
        destination: str,
        *,
        limit: int = 12,
        checkin: date | None = None,
        checkout: date | None = None,
    ) -> list[dict[str, Any]]:
        script_path = Path(__file__).with_name("google_hotel_extract.mjs")
        url = build_google_hotel_url(destination, checkin, checkout)
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
            raise GoogleHotelExtractionError("node 실행 파일을 찾지 못했습니다.") from exc
        except subprocess.TimeoutExpired as exc:
            raise GoogleHotelExtractionError("구글 호텔 화면 추출 시간이 초과되었습니다.") from exc
        if completed.returncode != 0:
            raise GoogleHotelExtractionError(
                completed.stderr.strip() or "구글 호텔 화면 추출에 실패했습니다."
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise GoogleHotelExtractionError(
                "구글 호텔 화면 출력 형식이 올바르지 않습니다."
            ) from exc
        results: list[dict[str, Any]] = []
        for hotel in payload.get("hotels", []):
            name = (hotel.get("name") or "").strip()
            amount = hotel.get("amount")
            if not name or not amount:
                continue
            results.append(
                {
                    "name": name,
                    "amount": int(amount),
                    "rating": hotel.get("rating"),
                    "star": hotel.get("star"),
                    "reviews": hotel.get("reviews"),
                    "amenities": hotel.get("amenities") or [],
                    # 도시 검색 URL이 아니라 '그 호텔 + 여행 날짜' 예약 링크를 넣는다.
                    "source_url": build_hotel_booking_url(name, checkin, checkout),
                }
            )
            if len(results) >= limit:
                break
        return results


# ── 객실/침대 타입 딥체크 ─────────────────────────────────────────────
# 호텔명으로 구글 호텔 상세를 열면 "더블룸 더블 사이즈 침대 1개 ₩222,348"처럼
# 객실 타입이 나온다. 사용자가 트윈/더블을 명시하면 상위 후보를 호텔별로 확인한다.

_PRICE_RE = re.compile(r"₩([\d,]{4,})")
_KIND_LABEL = {"twin": "트윈룸", "double": "더블룸"}
_KIND_PATTERNS = {
    "twin": re.compile(r"트윈|twin|트인|침대\s*2\s*개|싱글\s*침대\s*2"),
    "double": re.compile(r"더블|double|퀸|킹|queen|king"),
}
# 가격 옆에 표시되는 예약처(OTA) 이름. 가격 앞 구간에서 가장 가까운 것을 잡는다.
_OTA_PATTERNS = [
    ("부킹닷컴", re.compile(r"booking\.?com|부킹")),
    ("아고다", re.compile(r"agoda|아고다")),
    ("익스피디아", re.compile(r"expedia|익스피디아")),
    ("Hotels.com", re.compile(r"hotels\.?com|호텔스닷컴")),
    ("트립닷컴", re.compile(r"trip\.?com|트립닷컴|ctrip")),
    ("호텔 공식", re.compile(r"호텔\s*웹사이트|공식\s*사이트|official")),
]


def _detect_ota(window: str) -> str | None:
    # 가격에 가장 가까운(=윈도우에서 가장 오른쪽) OTA를 고른다.
    lowered = window.lower()
    best_name: str | None = None
    best_pos = -1
    for name, pattern in _OTA_PATTERNS:
        matches = list(pattern.finditer(lowered))
        if matches and matches[-1].start() > best_pos:
            best_pos = matches[-1].start()
            best_name = name
    return best_name


def detect_bed_preference(text: str | None) -> str | None:
    """선호 문구에서 침대 타입(twin/double)을 알아낸다. 없으면 None."""
    if not text:
        return None
    lowered = text.lower()
    if re.search(r"트윈|twin|트인|싱글\s*2|침대\s*2", lowered):
        return "twin"
    if re.search(r"더블|double|퀸|킹|queen|king", lowered):
        return "double"
    return None


def build_hotel_detail_url(hotel_name: str) -> str:
    return f"https://www.google.com/travel/search?q={quote_plus(hotel_name)}"


def parse_rooms(text: str) -> list[dict[str, Any]]:
    """상세 텍스트에서 (객실 설명, 가격) 목록을 뽑는다."""
    rooms: list[dict[str, Any]] = []
    for match in _PRICE_RE.finditer(text):
        price = int(match.group(1).replace(",", ""))
        # 침대 매칭은 가격 바로 앞 짧은 구간만(인접 객실 텍스트 오염 방지),
        # OTA 이름은 조금 더 넓게 본다(예약처가 보통 가격 앞에 적힘).
        desc = re.sub(r"\s+", " ", text[max(0, match.start() - 30) : match.start()]).strip()
        ota = _detect_ota(text[max(0, match.start() - 55) : match.start()])
        if desc:
            rooms.append({"desc": desc, "price": price, "ota": ota})
    return rooms


def match_room(rooms: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    """요청한 침대 타입과 맞는 객실 중 가장 싼 것을 고른다."""
    pattern = _KIND_PATTERNS.get(kind)
    if pattern is None:
        return None
    candidates = [room for room in rooms if pattern.search(room["desc"].lower())]
    if not candidates:
        return None
    return min(candidates, key=lambda room: room["price"])


def fetch_hotel_rooms(urls: list[str], *, timeout_seconds: int = 30) -> list[list[dict[str, Any]]]:
    """여러 호텔 상세를 브라우저 하나로 열어 객실 목록을 입력 순서대로 돌려준다."""
    if not urls:
        return []
    script_path = Path(__file__).with_name("google_hotel_rooms.mjs")
    concurrency = 3
    command = ["node", str(script_path), "--batch", str(timeout_seconds), str(concurrency)]
    batches = math.ceil(len(urls) / concurrency)
    total_timeout = timeout_seconds * batches + 15
    try:
        completed = subprocess.run(
            command,
            input="\n".join(urls),
            check=False,
            capture_output=True,
            encoding="utf-8",
            text=True,
            timeout=total_timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return [[] for _ in urls]
    results: list[list[dict[str, Any]]] = []
    for line in completed.stdout.splitlines():
        line = line.strip()
        if not line:
            results.append([])
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            results.append([])
            continue
        results.append(parse_rooms(item.get("text", "")))
    while len(results) < len(urls):
        results.append([])
    return results


def annotate_room_availability(
    options: list[AccommodationOption],
    *,
    preference: str | None,
    timeout_seconds: int = 30,
    max_checks: int = 6,
) -> list[AccommodationOption]:
    """침대 선호(트윈/더블)가 있으면 상위 호텔을 딥체크해 객실 유무를 표시하고 정렬한다.

    선호가 없으면 그대로 반환(빠른 경로 유지). 확인된 호텔을 앞으로 올린다.
    """
    kind = detect_bed_preference(preference)
    if not kind or not options:
        return options
    targets = options[:max_checks]
    urls = [build_hotel_detail_url(option.name) for option in targets]
    rooms_per_hotel = fetch_hotel_rooms(urls, timeout_seconds=timeout_seconds)
    label = _KIND_LABEL[kind]
    confirmed: list[AccommodationOption] = []
    others: list[AccommodationOption] = []
    for option, rooms in zip(targets, rooms_per_hotel, strict=False):
        room = match_room(rooms, kind) if rooms else None
        if room:
            ota = room.get("ota")
            ota_text = f" ({ota} 최저)" if ota else ""
            option.notes.insert(0, f"🛏 {label} 확인 · ₩{room['price']:,}~{ota_text}")
            confirmed.append(option)
        else:
            if rooms:
                option.notes.insert(0, f"🛏 {label} 미확인 — 예약 시 객실 타입 확인")
            others.append(option)
    return confirmed + others + options[max_checks:]
