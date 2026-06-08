"""구글 항공편 검색 화면 텍스트를 파싱해 FlightFareCandidate를 만든다.

구글 항공은 첫 화면에 '가는 편' 목록(출발/도착 시각·항공사·소요·경유·왕복 총액)을
보여준다. 오는 편 시각은 항공편을 선택해야 나오므로 여기선 inbound 정보를 비워 둔다.
네이버와 같은 FlightFareCandidate 스키마로 변환해 호출부가 동일하게 다룬다.
"""

from __future__ import annotations

import re

from travel_agent.app.schemas.llm import FlightFareCandidate

# 예: "오전 8:20 – 오전 11:00 진에어대한항공 2시간 40분 ICN–CTS 직항 ... ₩734,300 왕복"
_FLIGHT_RE = re.compile(
    r"(?P<dep_ampm>오전|오후)\s*(?P<dep_h>\d{1,2}):(?P<dep_m>\d{2})"
    r"\s*[–\-~]\s*"
    r"(?P<arr_ampm>오전|오후)\s*(?P<arr_h>\d{1,2}):(?P<arr_m>\d{2})(?:\s*\+\d)?"
    r"\s+(?P<airline>.+?)\s+"
    r"(?P<duration>\d+시간(?:\s*\d+분)?|\d+분)\s+"
    r"(?P<route>[A-Z]{3}(?:[–\-][A-Z]{3})+)\s+"
    r"(?P<stops>직항|\d+회\s*경유|경유)"
    r"[\s\S]*?₩(?P<price>[\d,]+)\s*(?P<trip>왕복|편도)"
)


def _to_24h(ampm: str, hour: int, minute: int) -> str:
    if ampm == "오전":
        hour = 0 if hour == 12 else hour
    else:  # 오후
        hour = 12 if hour == 12 else hour + 12
    return f"{hour:02d}:{minute:02d}"


def parse_google_flight_text(
    *, text: str, source_url: str, limit: int
) -> list[FlightFareCandidate]:
    candidates: list[FlightFareCandidate] = []
    seen: set[tuple[str, str, str]] = set()
    for match in _FLIGHT_RE.finditer(text):
        airline = match.group("airline").strip()
        # 항공사명이 비정상적으로 길면(다른 UI 텍스트가 섞임) 건너뛴다.
        if not airline or len(airline) > 30:
            continue
        outbound_departure = _to_24h(
            match.group("dep_ampm"), int(match.group("dep_h")), int(match.group("dep_m"))
        )
        outbound_arrival = _to_24h(
            match.group("arr_ampm"), int(match.group("arr_h")), int(match.group("arr_m"))
        )
        price = f"₩{match.group('price')} {match.group('trip')}"
        key = (airline, outbound_departure, price)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            FlightFareCandidate(
                provider="google_flights",
                airline=airline,
                outbound_departure=outbound_departure,
                outbound_arrival=outbound_arrival,
                inbound_departure=None,
                inbound_arrival=None,
                outbound_duration=match.group("duration").strip(),
                inbound_duration=None,
                price=price,
                stops=match.group("stops").strip(),
                source_url=source_url,
                notes=[],
            )
        )
        if len(candidates) >= limit:
            break
    return candidates
