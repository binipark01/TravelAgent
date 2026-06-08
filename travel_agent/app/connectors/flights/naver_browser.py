from __future__ import annotations

import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from travel_agent.app.schemas.common import StrictBaseModel
from travel_agent.app.schemas.llm import FlightFareCandidate

TIME_RE: Final = re.compile(r"^(?P<time>\d{2}:\d{2})(?P<airport>[A-Z]{3})$")
ROUTE_RE: Final = re.compile(
    r"/(?P<origin>[A-Z]{3})-(?P<destination>[A-Z]{3})-\d{8}"
)
ROUND_PRICE_RE: Final = re.compile(r"^왕복\s+[\d,]+원~$")
AIRLINE_TOKENS: Final = ("항공", "에어", "진에어", "피치")
CONTROL_LABELS: Final = {
    "왕복",
    "편도",
    "항공",
    "항공권",
    "직항만",
    "직항/경유",
    "항공사",
    "인기 항공편",
    "인기 항공편 보기",
    "왕복 동시 선택",
}


class NaverBrowserExtractionError(RuntimeError):
    pass


class NaverPageTextPayload(StrictBaseModel):
    text: str
    final_url: str | None = None


class NaverBatchItem(StrictBaseModel):
    url: str | None = None
    text: str = ""
    final_url: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class NaverFlightBrowserExtractor:
    timeout_seconds: int = 35
    # 두 소스(네이버+구글)를 한 브라우저에서 처리하므로 탭 동시성을 약간 높인다.
    batch_concurrency: int = 3

    def extract(self, source_url: str, *, limit: int = 5) -> list[FlightFareCandidate]:
        script_path = Path(__file__).with_name("naver_page_text.mjs")
        command = ["node", str(script_path), source_url, str(self.timeout_seconds)]
        completed = self._run(command, timeout=self.timeout_seconds + 5)
        try:
            payload = NaverPageTextPayload.model_validate_json(completed.stdout)
        except ValidationError as exc:
            raise NaverBrowserExtractionError(
                "Naver 항공권 화면 출력 형식이 올바르지 않습니다."
            ) from exc
        return parse_naver_flight_text(
            text=payload.text,
            source_url=payload.final_url or source_url,
            limit=limit,
        )

    def fetch_pages(self, source_urls: list[str]) -> list[NaverBatchItem]:
        """여러 URL을 브라우저 하나로 렌더링해 원문 텍스트를 입력 순서대로 돌려준다.

        파싱은 하지 않는다(네이버/구글 등 소스별 파서를 호출부에서 고르게 한다).
        날짜별 Chrome 콜드스타트를 피하고 CPU를 낮춘다. 일부 페이지가 실패해도 그
        항목만 빈 텍스트가 되고 전체는 계속 진행한다.
        """
        if not source_urls:
            return []
        script_path = Path(__file__).with_name("naver_page_text.mjs")
        command = [
            "node",
            str(script_path),
            "--batch",
            str(self.timeout_seconds),
            str(self.batch_concurrency),
        ]
        # 동시성 만큼 묶어서 순차 처리하므로 배치 전체 타임아웃을 넉넉히 잡는다.
        batches = math.ceil(len(source_urls) / max(self.batch_concurrency, 1))
        batch_timeout = self.timeout_seconds * batches + 15
        completed = self._run(command, timeout=batch_timeout, stdin="\n".join(source_urls))
        items: list[NaverBatchItem] = []
        for index, line in enumerate(completed.stdout.splitlines()):
            line = line.strip()
            fallback_url = source_urls[index] if index < len(source_urls) else None
            if not line:
                items.append(NaverBatchItem(url=fallback_url))
                continue
            try:
                items.append(NaverBatchItem.model_validate_json(line))
            except ValidationError:
                items.append(NaverBatchItem(url=fallback_url))
        # 출력 줄 수가 입력보다 적으면 빈 항목으로 채워 순서를 보존한다.
        while len(items) < len(source_urls):
            items.append(NaverBatchItem(url=source_urls[len(items)]))
        return items

    def extract_many(
        self, source_urls: list[str], *, limit: int = 5
    ) -> list[list[FlightFareCandidate]]:
        """여러 네이버 URL을 한 브라우저로 처리해 후보 리스트를 입력 순서대로 돌려준다."""
        items = self.fetch_pages(source_urls)
        results: list[list[FlightFareCandidate]] = []
        for item, src in zip(items, source_urls, strict=False):
            results.append(
                parse_naver_flight_text(
                    text=item.text,
                    source_url=item.final_url or item.url or src,
                    limit=limit,
                )
            )
        return results

    def _run(
        self, command: list[str], *, timeout: int, stdin: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                encoding="utf-8",
                text=True,
                timeout=timeout,
                input=stdin,
            )
        except FileNotFoundError as exc:
            raise NaverBrowserExtractionError("node 실행 파일을 찾지 못했습니다.") from exc
        except subprocess.TimeoutExpired as exc:
            raise NaverBrowserExtractionError(
                "Naver 항공권 화면 추출 시간이 초과되었습니다."
            ) from exc
        if completed.returncode != 0:
            message = completed.stderr.strip() or "Naver 항공권 화면 추출에 실패했습니다."
            raise NaverBrowserExtractionError(message)
        return completed


def parse_naver_flight_text(
    *, text: str, source_url: str, limit: int
) -> list[FlightFareCandidate]:
    route = _route_from_source_url(source_url)
    if route is None:
        return []
    origin, destination = route
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    options: list[FlightFareCandidate] = []
    seen: set[tuple[str, str, str, str | None, str | None, str]] = set()
    index = 0
    while index < len(lines) and len(options) < limit:
        airline = lines[index]
        if not _looks_like_airline(airline):
            index += 1
            continue
        candidate = _candidate_from_lines(
            lines=lines,
            start=index,
            origin=origin,
            destination=destination,
            source_url=source_url,
        )
        if candidate is None:
            index += 1
            continue
        key = (
            candidate.airline,
            candidate.outbound_departure,
            candidate.outbound_arrival,
            candidate.inbound_departure,
            candidate.inbound_arrival,
            candidate.price,
        )
        if key not in seen:
            options.append(candidate)
            seen.add(key)
        index += 1
    return options


def _candidate_from_lines(
    *,
    lines: list[str],
    start: int,
    origin: str,
    destination: str,
    source_url: str,
) -> FlightFareCandidate | None:
    price_index = _find_round_price(lines, start)
    if price_index is None:
        return None
    outbound = _find_time_pair(lines, start + 1, price_index, origin, destination)
    if outbound is None:
        return None
    inbound = _find_time_pair(lines, outbound.end_index, price_index, destination, origin)
    price = lines[price_index]
    notes = [
        line
        for line in lines[max(start, price_index - 3) : min(len(lines), price_index + 3)]
        if "할인" in line or "적립" in line
    ]
    return FlightFareCandidate(
        provider="naver_flight",
        airline=lines[start],
        outbound_departure=_format_time(outbound.departure),
        outbound_arrival=_format_time(outbound.arrival),
        inbound_departure=_format_time(inbound.departure) if inbound else None,
        inbound_arrival=_format_time(inbound.arrival) if inbound else None,
        outbound_duration=outbound.duration,
        inbound_duration=inbound.duration if inbound else None,
        price=price,
        stops=_stops_label(outbound.duration, inbound.duration if inbound else None),
        source_url=source_url,
        notes=notes,
    )


@dataclass(frozen=True, slots=True)
class TimePair:
    departure: str
    arrival: str
    duration: str | None
    end_index: int


def _find_time_pair(
    lines: list[str], start: int, end: int, departure_airport: str, arrival_airport: str
) -> TimePair | None:
    for index in range(start, max(start, end - 1)):
        departure = _parse_time(lines[index])
        arrival = _parse_time(lines[index + 1])
        if not departure or not arrival:
            continue
        if departure[1] != departure_airport or arrival[1] != arrival_airport:
            continue
        duration = lines[index + 2] if index + 2 < end and _is_duration(lines[index + 2]) else None
        return TimePair(
            departure=lines[index],
            arrival=lines[index + 1],
            duration=duration,
            end_index=index + 3 if duration else index + 2,
        )
    return None


def _route_from_source_url(source_url: str) -> tuple[str, str] | None:
    match = ROUTE_RE.search(source_url)
    if match is None:
        return None
    return match.group("origin"), match.group("destination")


def _find_round_price(lines: list[str], start: int) -> int | None:
    for index in range(start + 1, min(len(lines), start + 40)):
        if ROUND_PRICE_RE.match(lines[index]):
            return index
    return None


def _parse_time(line: str) -> tuple[str, str] | None:
    match = TIME_RE.match(line)
    if match is None:
        return None
    return match.group("time"), match.group("airport")


def _format_time(line: str) -> str:
    parsed = _parse_time(line)
    if parsed is None:
        return line
    return f"{parsed[0]} {parsed[1]}"


def _looks_like_airline(line: str) -> bool:
    if line in CONTROL_LABELS or ROUND_PRICE_RE.match(line) or _parse_time(line):
        return False
    if line[0].isdigit() or "항공편" in line or "더보기" in line:
        return False
    if _is_duration(line) or "원" in line or "할인" in line or "적립" in line:
        return False
    return any(token in line for token in AIRLINE_TOKENS)


def _is_duration(line: str) -> bool:
    return "시간" in line and "분" in line


def _stops_label(outbound_duration: str | None, inbound_duration: str | None) -> str:
    durations = [duration for duration in [outbound_duration, inbound_duration] if duration]
    if durations and all(duration.startswith("직항") for duration in durations):
        return "직항"
    return "경유 포함"
