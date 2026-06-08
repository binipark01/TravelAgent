from __future__ import annotations

FRESHNESS_POLICIES: dict[str, str] = {
    "flight": "short_ttl_reprice_before_booking",
    "accommodation": "short_ttl_recheck_before_booking",
    "poi": "medium_ttl_recheck_opening_hours_for_visit_date",
    "activity": "medium_ttl_recheck_availability_before_booking",
    "route": "medium_short_ttl_recompute_near_trip",
    "visa": "official_verification_required_before_booking",
    "safety": "official_verification_required",
    "weather": "short_ttl",
    "fx": "medium_ttl",
}


def freshness_policy_for(category: str) -> str:
    return FRESHNESS_POLICIES.get(category, "verify_before_booking")
