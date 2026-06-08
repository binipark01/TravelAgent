from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from travel_agent.app.connectors.base import ConnectorResult
from travel_agent.app.evidence.models import EvidenceSourceRef
from travel_agent.app.schemas.providers import AccommodationSearchRequest
from travel_agent.app.utils.time import expires_in, utc_now

JAPAN_DESTINATIONS: Final[frozenset[str]] = frozenset(
    {"Osaka", "오사카", "Tokyo", "도쿄", "Sapporo", "삿포로", "Fukuoka", "후쿠오카"}
)

_BUDGET_HINTS: Final[frozenset[str]] = frozenset(
    {"budget", "저렴", "가성비", "hostel", "guesthouse", "게스트하우스", "호스텔", "cheap"}
)
_PREMIUM_HINTS: Final[frozenset[str]] = frozenset(
    {"luxury", "프리미엄", "고급", "resort", "리조트", "5성", "5-star", "five-star", "spa"}
)


@dataclass(frozen=True)
class MockAccommodationSearchConnector:
    name: str = "mock_accommodation"
    source_type: str = "mock"

    def collect(self, request: AccommodationSearchRequest) -> ConnectorResult:
        nights = max((request.check_out - request.check_in).days, 1)
        standard_nightly = 150_000 if request.destination in {"Osaka", "오사카"} else 135_000
        country = "Japan" if request.destination in JAPAN_DESTINATIONS else None
        now = utc_now()

        tiers: list[dict[str, Any]] = [
            {
                "tier": "budget",
                "name": f"{request.destination} Mock Budget Inn",
                "area": "Station-side",
                "nightly": int(round(standard_nightly * 0.7, -3)),
                "rating": 3.9,
                "cancellation_policy": "Simulated non-refundable budget rate.",
                "label": "가성비 · 역세권",
            },
            {
                "tier": "standard",
                "name": f"{request.destination} Mock Central Hotel",
                "area": "Central",
                "nightly": standard_nightly,
                "rating": 4.2,
                "cancellation_policy": (
                    "Simulated flexible cancellation until 48h before check-in."
                ),
                "label": "스탠다드 · 시내 중심",
            },
            {
                "tier": "premium",
                "name": f"{request.destination} Mock Grand Suite",
                "area": "Downtown",
                "nightly": int(round(standard_nightly * 1.6, -3)),
                "rating": 4.7,
                "cancellation_policy": (
                    "Simulated free cancellation until 24h before check-in."
                ),
                "label": "프리미엄 · 환불 유연",
            },
        ]
        ordered = self._order_by_preference(tiers, request.preference)

        normalized_items = [
            {
                "name": tier["name"],
                "area": tier["area"],
                "country": country,
                "nightly_amount": tier["nightly"],
                "total_amount": tier["nightly"] * nights,
                "currency": request.currency,
                "rating": tier["rating"],
                "cancellation_policy": tier["cancellation_policy"],
                "notes": [
                    f"{tier['label']} ({nights}박)",
                    "Mock availability only; verify hotel terms before booking.",
                    "No live accommodation network request was made.",
                ],
            }
            for tier in ordered
        ]
        return ConnectorResult(
            source_ref=EvidenceSourceRef(
                provider=self.name,
                provider_ref=f"mock-hotel-{now.strftime('%Y%m%d%H%M%S')}",
                retrieved_at=now,
                expires_at=expires_in(12),
                is_live=False,
                is_mock=True,
                source_type=self.source_type,
                confidence=0.4,
                attribution="MVP mock accommodation connector",
                license_notes="Dev/test fallback only; not a live source.",
            ),
            raw_payload={
                "mock": True,
                "destination": request.destination,
                "check_in": request.check_in.isoformat(),
                "check_out": request.check_out.isoformat(),
                "preference": request.preference,
            },
            normalized_items=normalized_items,
        )

    @staticmethod
    def _order_by_preference(
        tiers: list[dict[str, Any]], preference: str | None
    ) -> list[dict[str, Any]]:
        text = (preference or "").lower()
        if any(hint in text for hint in _BUDGET_HINTS):
            priority = {"budget": 0, "standard": 1, "premium": 2}
        elif any(hint in text for hint in _PREMIUM_HINTS):
            priority = {"premium": 0, "standard": 1, "budget": 2}
        else:
            priority = {"standard": 0, "budget": 1, "premium": 2}
        return sorted(tiers, key=lambda tier: priority[tier["tier"]])
