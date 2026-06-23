"""서버 전체 파이프라인으로 첫날 도착공항·마지막날 출국공항을 검증하는 프로브.

POST /agent/runs로 일정을 만들고 폴링해, day1 첫 항목과 마지막 날 마지막 항목이 공항인지,
그리고 공항↔도심 이동(transfer)이 들어갔는지 출력한다.

사용: python scripts/airport_api_probe.py "오사카 3박4일 여행 일정 짜줘"
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8000/agent/runs"


def _post(message: str) -> dict:
    body = json.dumps({"message": message}).encode("utf-8")
    req = urllib.request.Request(BASE, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(run_id: str) -> dict:
    with urllib.request.urlopen(f"{BASE}/{run_id}", timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _is_airport(title: str) -> bool:
    return any(k in (title or "") for k in ("공항", "空港", "airport", "Airport"))


def main() -> None:
    message = sys.argv[1] if len(sys.argv) > 1 else "오사카 3박4일 여행 일정 짜줘"
    started = _post(message)
    run_id = started["run_id"]
    print(f"run_id={run_id}", flush=True)
    itinerary = None
    for _ in range(150):  # 최대 ~5분
        time.sleep(2)
        detail = _get(run_id)
        state = detail.get("state") or {}
        itin = state.get("optimized_itinerary")
        status = detail["run"]["status"]
        if itin and itin.get("days"):
            itinerary = itin
            if status in ("completed", "failed", "cancelled", "waiting_for_user"):
                break
        if status in ("failed", "cancelled"):
            break
    if not itinerary:
        print("일정 생성 실패/미완", flush=True)
        return
    days = itinerary["days"]
    out_lines = [f"\n===== {message} → {len(days)}일 ====="]
    for d in days:
        items = d.get("items") or []
        transfers = d.get("transfers") or []
        first = items[0]["title"] if items else "(빈 날)"
        last = items[-1]["title"] if items else "(빈 날)"
        flags = []
        if d["day"] == 1:
            flags.append("✅도착공항" if _is_airport(first) else "❌첫날 공항없음")
        if d["day"] == len(days):
            flags.append("✅출국공항" if _is_airport(last) else "❌마지막날 공항없음")
        out_lines.append(
            f"  Day{d['day']} [{d.get('area')}] 항목{len(items)}/이동{len(transfers)}: "
            f"첫={first} / 끝={last}  {' '.join(flags)}"
        )
        # 첫날·마지막날은 공항 이동이 보이게 transfer도 출력
        if d["day"] in (1, len(days)):
            for t in transfers[:2] if d["day"] == 1 else transfers[-2:]:
                out_lines.append(
                    f"      ↳ 이동: {t['origin']} → {t['destination']} "
                    f"({t['mode']} {t['travel_minutes']}분)"
                )
    text = "\n".join(out_lines)
    with open("scripts/_airport_api_out.txt", "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text.encode("ascii", "replace").decode("ascii"), flush=True)
    print("\n(원문 UTF-8: scripts/_airport_api_out.txt)", flush=True)


if __name__ == "__main__":
    main()
