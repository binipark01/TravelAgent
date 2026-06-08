from __future__ import annotations

from sqlalchemy.orm import Session

from travel_agent.app.db.repositories import TripRepository
from travel_agent.app.schemas.trip import TripPlanState


class SnapshotService:
    def __init__(self, session: Session) -> None:
        self.repository = TripRepository(session)

    def save(self, state: TripPlanState) -> int:
        return self.repository.save_snapshot(state)
