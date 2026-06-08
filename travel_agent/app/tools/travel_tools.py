from __future__ import annotations

from typing import Any

from travel_agent.app.evidence.freshness import freshness_policy_for
from travel_agent.app.evidence.models import EvidenceCategory, EvidencePacket, EvidenceSourceRef
from travel_agent.app.evidence.store import EvidenceStore
from travel_agent.app.schemas.common import SourceRef
from travel_agent.app.schemas.trip import TripPlanState
from travel_agent.app.sources.source_discovery import SourceDiscoveryTool
from travel_agent.app.utils.ids import new_id


class ToolExecutor:
    def __init__(
        self, evidence_store: EvidenceStore, source_discovery: SourceDiscoveryTool
    ) -> None:
        self.evidence_store = evidence_store
        self.source_discovery = source_discovery

    def discover_sources(self, domain: str) -> dict[str, list[str]]:
        enabled, rejected = self.source_discovery.discover(domain)
        return {
            "enabled": [source.name for source in enabled],
            "rejected": [source.name for source in rejected],
        }

    def store_state_outputs(
        self,
        *,
        run_id: str,
        state: TripPlanState,
        agent_name: str,
    ) -> list[EvidencePacket]:
        packets: list[EvidencePacket] = []
        packets.extend(
            self._packets_from_items(
                run_id=run_id,
                state=state,
                agent_name=agent_name,
                tool_name="SearchFlightsTool",
                category=EvidenceCategory.flight,
                items=state.transport_options,
            )
        )
        packets.extend(
            self._packets_from_items(
                run_id=run_id,
                state=state,
                agent_name=agent_name,
                tool_name="SearchAccommodationsTool",
                category=EvidenceCategory.accommodation,
                items=state.accommodation_options,
            )
        )
        packets.extend(
            self._packets_from_items(
                run_id=run_id,
                state=state,
                agent_name=agent_name,
                tool_name="SearchPOIsTool",
                category=EvidenceCategory.poi,
                items=state.poi_candidates,
            )
        )
        if state.visa_result:
            packets.extend(
                self._packets_from_items(
                    run_id=run_id,
                    state=state,
                    agent_name=agent_name,
                    tool_name="CheckVisaRiskTool",
                    category=EvidenceCategory.visa,
                    items=[state.visa_result],
                )
            )
        if state.optimized_itinerary:
            packets.append(
                EvidencePacket(
                    trip_id=state.trip_id,
                    run_id=run_id,
                    category=EvidenceCategory.route,
                    normalized_data=state.optimized_itinerary.model_dump(mode="json"),
                    source_refs=[],
                    collected_by_agent="RouteAgent",
                    collected_by_tool="ComputeRoutesTool",
                    freshness_policy=freshness_policy_for("route"),
                    confidence=0.45,
                )
            )
        saved = self.evidence_store.save_many(packets)
        for packet in saved:
            if packet.evidence_id not in state.evidence_refs:
                state.evidence_refs.append(packet.evidence_id)
        return saved

    def _packets_from_items(
        self,
        *,
        run_id: str,
        state: TripPlanState,
        agent_name: str,
        tool_name: str,
        category: EvidenceCategory,
        items: list[Any],
    ) -> list[EvidencePacket]:
        packets: list[EvidencePacket] = []
        for item in items:
            data = item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
            source_ref = data.get("metadata", {}).get("source_ref")
            source_refs = [self._to_evidence_source_ref(source_ref)] if source_ref else []
            packets.append(
                EvidencePacket(
                    evidence_id=new_id("evidence"),
                    trip_id=state.trip_id,
                    run_id=run_id,
                    category=category,
                    normalized_data=data,
                    source_refs=source_refs,
                    collected_by_agent=agent_name,
                    collected_by_tool=tool_name,
                    freshness_policy=freshness_policy_for(category.value),
                    confidence=0.4 if any(ref.is_mock for ref in source_refs) else 0.8,
                )
            )
        return packets

    def _to_evidence_source_ref(self, ref: dict[str, Any] | SourceRef) -> EvidenceSourceRef:
        data = ref.model_dump(mode="json") if hasattr(ref, "model_dump") else ref
        return EvidenceSourceRef(
            source_id=data["source_id"],
            provider=data["provider"],
            provider_ref=data.get("provider_ref") or data.get("reference"),
            source_url=data.get("source_url"),
            retrieved_at=data["retrieved_at"],
            expires_at=data.get("expires_at"),
            is_live=data.get("is_live", False),
            is_mock=data.get("is_mock", True),
            source_type=data.get("source_type", "mock"),
            confidence=data.get("confidence", 0.5),
            attribution=data.get("attribution"),
            license_notes=data.get("license_notes"),
        )
