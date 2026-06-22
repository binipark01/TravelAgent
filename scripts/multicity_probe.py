"""동반 도시 자동 편성 + 일정 품질을 여러 도시로 라이브 점검하는 개발 프로브.

사용: python scripts/multicity_probe.py [도시1 도시2 ...]
백엔드(http://127.0.0.1:8000)가 떠 있어야 한다. 도시당 3박4일 종합 계획을 만들고,
동반 도시(교토 같은)·근교일·일정 품질(빈 날·중복 POI)을 한 줄로 진단한다. 동시 3개.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "http://127.0.0.1:8000"

DEFAULT_CITIES = ["도쿄", "방콕", "싱가포르", "두바이", "파리", "타이베이"]


def _post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def _get(path: str) -> dict:
    return json.loads(urllib.request.urlopen(BASE + path, timeout=60).read())


def _city_of(area: str | None) -> str:
    if not area:
        return "?"
    area = area.strip()
    if area.startswith("근교"):
        return "근교:" + area.split(":", 1)[-1].strip().split("·")[0].strip()
    return area.split("·")[0].strip()


def probe(city: str) -> str:
    try:
        created = _post(
            "/agent/runs",
            {
                "message": f"{city} 3박4일 여행 일정 짜줘",
                "locale": "ko-KR",
                "currency": "KRW",
                "timezone": "Asia/Seoul",
            },
        )
        rid = created["run_id"]
        status = "?"
        detail = {}
        for _ in range(360):
            detail = _get(f"/agent/runs/{rid}")
            status = detail["run"]["status"]
            if status in ("completed", "failed", "cancelled", "waiting_for_user"):
                break
            time.sleep(2)
        state = detail.get("state", {})
        base = state.get("selected_destination") or city
        itinerary = state.get("optimized_itinerary") or {}
        days = itinerary.get("days") or []
        areas = [d.get("area") for d in days]
        day_cities = [_city_of(a) for a in areas]
        # 멀티시티일 때만 배치기가 모든 날 area에 '도시 · 동네' 접두사를 붙인다. 본거지가
        # 접두사로 등장하지 않으면 단일 도시(동반 없음)로 본다 — 파리 구역명 오탐 방지.
        base_first = base.split(",")[0].strip().lower()
        multi = any((a or "").strip().lower().startswith(base_first) for a in areas)
        companions = sorted(
            {c for c in day_cities if c != "?" and not c.startswith("근교") and c.lower() != base_first}
        ) if multi else []
        nearby_days = [c for c in day_cities if c.startswith("근교")]
        # 품질 점검
        all_titles: list[str] = []
        empty_days = 0
        for d in days:
            items = d.get("items", [])
            if not items:
                empty_days += 1
            all_titles += [i["title"] for i in items]
        dups = len(all_titles) - len(set(all_titles))
        comp = f"동반:{','.join(companions)}" if companions else "동반:없음"
        nb = f" 근교:{len(nearby_days)}일" if nearby_days else ""
        return (
            f"[{city}] {status} | {len(days)}일 | base={base}\n"
            f"     areas={areas}\n"
            f"     {comp}{nb} | POI {len(all_titles)} | 중복 {dups} | 빈날 {empty_days}"
        )
    except Exception as exc:  # noqa: BLE001
        return f"[{city}] ERROR: {exc}"


def main() -> None:
    cities = sys.argv[1:] or DEFAULT_CITIES
    print(f"=== 동반 도시 스윕: {', '.join(cities)} ===", flush=True)
    with ThreadPoolExecutor(max_workers=3) as executor:
        for result in executor.map(probe, cities):
            print(result, flush=True)


if __name__ == "__main__":
    main()
