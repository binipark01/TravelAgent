from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from travel_agent.app.db.models import EvidencePacketModel
from travel_agent.app.evidence.models import EvidenceCategory, EvidencePacket


class EvidenceStore:
    def __init__(self, session: Session | None = None) -> None:
        self.session = session
        self._memory: dict[str, EvidencePacket] = {}

    def save(self, packet: EvidencePacket) -> EvidencePacket:
        if self.session is None:
            self._memory[packet.evidence_id] = packet
            return packet
        self.session.add(
            EvidencePacketModel(
                evidence_id=packet.evidence_id,
                trip_id=packet.trip_id,
                run_id=packet.run_id,
                category=packet.category.value,
                normalized_data_json=packet.normalized_data,
                source_refs_json=[ref.model_dump(mode="json") for ref in packet.source_refs],
                collected_by_agent=packet.collected_by_agent,
                collected_by_tool=packet.collected_by_tool,
                created_at=packet.created_at,
                expires_at=packet.expires_at,
                freshness_policy=packet.freshness_policy,
                confidence=packet.confidence,
            )
        )
        self._memory[packet.evidence_id] = packet
        return packet

    def save_many(self, packets: list[EvidencePacket]) -> list[EvidencePacket]:
        return [self.save(packet) for packet in packets]

    def list_by_trip(
        self, trip_id: str, category: EvidenceCategory | str | None = None
    ) -> list[EvidencePacket]:
        if self.session is None:
            return [
                packet
                for packet in self._memory.values()
                if packet.trip_id == trip_id
                and (category is None or packet.category == EvidenceCategory(str(category)))
            ]
        stmt = select(EvidencePacketModel).where(EvidencePacketModel.trip_id == trip_id)
        if category:
            stmt = stmt.where(EvidencePacketModel.category == str(category))
        return [self._to_packet(model) for model in self.session.execute(stmt).scalars()]

    def list_by_run(
        self, run_id: str, category: EvidenceCategory | str | None = None
    ) -> list[EvidencePacket]:
        if self.session is None:
            return [
                packet
                for packet in self._memory.values()
                if packet.run_id == run_id
                and (category is None or packet.category == EvidenceCategory(str(category)))
            ]
        stmt = select(EvidencePacketModel).where(EvidencePacketModel.run_id == run_id)
        if category:
            stmt = stmt.where(EvidencePacketModel.category == str(category))
        return [self._to_packet(model) for model in self.session.execute(stmt).scalars()]

    def get(self, evidence_id: str) -> EvidencePacket | None:
        if self.session is None:
            return self._memory.get(evidence_id)
        model = self.session.get(EvidencePacketModel, evidence_id)
        return self._to_packet(model) if model else None

    def mark_stale(self, evidence_id: str) -> None:
        packet = self.get(evidence_id)
        if packet:
            packet.confidence = min(packet.confidence, 0.2)

    def summarize_for_agent(self, trip_id: str, category: str) -> dict[str, object]:
        packets = self.list_by_trip(trip_id, category)
        return {
            "category": category,
            "count": len(packets),
            "evidence_ids": [packet.evidence_id for packet in packets],
            "mock_count": sum(any(ref.is_mock for ref in packet.source_refs) for packet in packets),
        }

    def _to_packet(self, model: EvidencePacketModel) -> EvidencePacket:
        return EvidencePacket.model_validate(
            {
                "evidence_id": model.evidence_id,
                "trip_id": model.trip_id,
                "run_id": model.run_id,
                "category": model.category,
                "normalized_data": model.normalized_data_json,
                "source_refs": model.source_refs_json,
                "collected_by_agent": model.collected_by_agent,
                "collected_by_tool": model.collected_by_tool,
                "created_at": model.created_at,
                "expires_at": model.expires_at,
                "freshness_policy": model.freshness_policy,
                "confidence": model.confidence,
            }
        )
