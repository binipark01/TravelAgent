"""도시별 큐레이션 품질 프로브(임시). 관광지·식당 다양성·출처를 한눈에 본다.

사용: python scripts/curation_probe.py <도시> [관심사]
"""

from __future__ import annotations

import re
import sys

from travel_agent.app.llm import curator


def host(url: str | None) -> str:
    m = re.search(r"https?://([^/]+)", url or "")
    return m.group(1) if m else (url or "-")


def main() -> None:
    city = sys.argv[1] if len(sys.argv) > 1 else "방콕"
    interests = sys.argv[2].split(",") if len(sys.argv) > 2 else ["맛집"]
    print(f"\n===== {city} (관심사: {interests}) =====")

    pois = curator.curate_city_pois(
        city, interests=interests, start_date=None, currency="KRW",
        attraction_pool=[], restaurant_pool=[],
    )
    if not pois:
        print("  POIs: NONE (LLM 비활성?)")
    else:
        print(f"  관광지 {len(pois.attractions)} / 식당 {len(pois.restaurants)}")
        print("  [관광지 유형]", [a.type for a in pois.attractions])
        print("  [식당 유형  ]", [r.type for r in pois.restaurants])
        attr_hosts = sorted({host(a.metadata.source_ref.source_url) for a in pois.attractions})
        rest_hosts = sorted({host(r.metadata.source_ref.source_url) for r in pois.restaurants})
        print("  [관광지 출처]", attr_hosts)
        print("  [식당 출처  ]", rest_hosts)
        booked = [a.title for a in pois.attractions if a.booking_required]
        print("  [예약필요   ]", booked)

    stay = curator.curate_stay_areas(city)
    if stay:
        print("  [숙박구역   ]", [a.name for a in stay.areas])

    near = curator.curate_nearby(city)
    if near:
        print("  [근교       ]", [d.name for d in near.destinations])


if __name__ == "__main__":
    main()
