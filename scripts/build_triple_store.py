"""트리플 실코스 데이터셋(.omo, 592MB JSONL)을 런타임용 '컴팩트 코스 스토어'로 distill한다.

원본은 너무 커서 매번 파싱 불가. 한 번 돌려 도시별 작은 JSON으로 뽑아두고, 런타임 커넥터는
요청 도시 파일 1개만 지연 로드한다. 산출: .omo/triple-store/{도시}.json
  {
    "pois": { "정규화이름": [lat, lng, rating, category, type, 원본이름], ... },
    "courses": { "기간|동행|스타일|피로도": [["POI원본명", ...](day1), [..](day2), ...], ... }
  }
도시당 키 756개(기간6×동행7×스타일9×피로도2), 키당 1코스.

사용: python scripts/build_triple_store.py
"""

from __future__ import annotations

import json
import os
import re

SRC = r".omo\triple-all-cases\actual-schedules-merged\schedule_cases.jsonl"
OUT_DIR = r".omo\triple-store"


def _norm(name: str) -> str:
    """POI 이름 정규화(공백·괄호·구분자 제거, 소문자) — 매칭용 키."""
    s = re.sub(r"\(.*?\)", "", name or "")
    s = re.sub(r"[\s·,./\-—~]", "", s)
    return s.strip().lower()


def main() -> None:
    if not os.path.exists(SRC):
        print(f"원본 없음: {SRC}")
        return
    os.makedirs(OUT_DIR, exist_ok=True)
    # city -> {"pois": {norm: [...]}, "courses": {key: [[names]...]}}
    store: dict[str, dict] = {}
    n = 0
    with open(SRC, encoding="utf-8") as fh:
        for line in fh:
            n += 1
            rec = json.loads(line)
            lab = rec.get("labels") or {}
            city = lab.get("city")
            if not city:
                continue
            entry = store.setdefault(city, {"pois": {}, "courses": {}})
            styles = lab.get("style") or []
            style = styles[0] if styles else ""
            key = f"{lab.get('period')}|{lab.get('who')}|{style}|{lab.get('fatigue')}"
            course_days: list[list[str]] = []
            for day in rec.get("days") or []:
                names: list[str] = []
                for it in day.get("items") or []:
                    name = (it.get("poiName") or "").strip()
                    if not name:
                        continue
                    names.append(name)
                    norm = _norm(name)
                    if norm and norm not in entry["pois"]:
                        geo = (it.get("geolocation") or {}).get("coordinates") or [None, None]
                        meta = it.get("metadata") or {}
                        entry["pois"][norm] = [
                            round(geo[1], 6) if geo[1] is not None else None,  # lat
                            round(geo[0], 6) if geo[0] is not None else None,  # lng
                            meta.get("reviewsRating"),
                            it.get("category"),
                            it.get("type"),
                            name,
                        ]
                course_days.append(names)
            entry["courses"][key] = course_days
            if n % 5000 == 0:
                print(f"  ...{n} cases", flush=True)
    for city, entry in store.items():
        path = os.path.join(OUT_DIR, f"{city}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(entry, fh, ensure_ascii=False)
        print(
            f"  {city}: pois={len(entry['pois'])} courses={len(entry['courses'])} -> {path}",
            flush=True,
        )
    print(f"완료: {len(store)}개 도시, 총 {n} 케이스")


if __name__ == "__main__":
    main()
