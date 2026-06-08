from __future__ import annotations

from travel_agent.app.db.repositories import TripRepository
from travel_agent.app.schemas.trip import TripPlanState


class CheckpointStore:
    def __init__(self, repository: TripRepository) -> None:
        self.repository = repository

    def save(self, state: TripPlanState) -> int:
        return self.repository.save_snapshot(state)
