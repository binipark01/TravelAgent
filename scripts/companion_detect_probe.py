"""동반 도시 판단(curate_companion_cities)을 여러 도시로 빠르게 검증하는 개발 프로브.

풀플랜 없이 동반 도시 LLM 웹검색만 도시별로 돌려, 지역별 판단이 합리적인지 본다
(짝 있는 곳은 넣고, 섬·도시국가처럼 짝 없는 곳은 안 넣는지). 동시 4개.

사용: python scripts/companion_detect_probe.py
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from travel_agent.app.llm.curator import curate_companion_cities

REGIONS: dict[str, list[str]] = {
    "유럽": [
        "파리", "로마", "바르셀로나", "런던", "암스테르담",
        "프라하", "비엔나", "베네치아", "피렌체", "마드리드",
        "리스본", "뮌헨", "베를린", "부다페스트", "취리히",
        "인터라켄", "산토리니", "아테네", "두브로브니크", "니스",
    ],
    "아시아": [
        "후쿠오카", "삿포로", "다낭", "홍콩", "상하이",
        "발리", "하노이", "세부", "푸켓", "싱가포르",
    ],
    "아메리카": [
        "뉴욕", "로스앤젤레스", "라스베이거스", "샌프란시스코", "시카고",
        "토론토", "밴쿠버", "칸쿤", "멕시코시티", "호놀룰루",
    ],
}


def detect(city: str) -> tuple[str, str]:
    try:
        comps = curate_companion_cities(city, 4)
        if not comps:
            return city, "(없음)"
        return city, "; ".join(f"{c.city} {c.days}일" for c in comps)
    except Exception as exc:  # noqa: BLE001
        return city, f"ERROR {exc}"


def main() -> None:
    all_cities = [c for cities in REGIONS.values() for c in cities]
    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        for city, summary in executor.map(detect, all_cities):
            results[city] = summary
            print(f"  done: {city}", flush=True)
    print("\n===== 동반 도시 판단 결과 =====", flush=True)
    for region, cities in REGIONS.items():
        print(f"\n[{region}]", flush=True)
        for city in cities:
            print(f"  {city:14s} → {results.get(city, '?')}", flush=True)


if __name__ == "__main__":
    main()
