from __future__ import annotations

from travel_agent.app.evidence.models import EvidencePacket


def rank_evidence(packets: list[EvidencePacket]) -> list[EvidencePacket]:
    return sorted(
        packets,
        key=lambda packet: (packet.confidence, packet.created_at),
        reverse=True,
    )
