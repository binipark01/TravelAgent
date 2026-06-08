"""구글 호텔 검색 화면을 브라우저로 분석해 실제 숙소 후보를 만든다.

`google_hotel_extract.mjs`가 호텔 카드(aria-label)에서 이름·가격·평점을 구조적으로
추출해 JSON으로 돌려준다. 추출이 실패하면 빈 목록을 반환한다(mock 미사용).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from travel_agent.app.connectors.accommodations.naver_hotel_browser import build_hotel_query


class GoogleHotelExtractionError(RuntimeError):
    pass


def build_google_hotel_url(destination: str) -> str:
    return f"https://www.google.com/travel/search?q={quote_plus(build_hotel_query(destination))}"


@dataclass(frozen=True, slots=True)
class GoogleHotelBrowserExtractor:
    timeout_seconds: int = 35

    def extract(self, destination: str, *, limit: int = 12) -> list[dict[str, Any]]:
        script_path = Path(__file__).with_name("google_hotel_extract.mjs")
        url = build_google_hotel_url(destination)
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
        final_url = payload.get("final_url") or url
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
                    "source_url": final_url,
                }
            )
            if len(results) >= limit:
                break
        return results
