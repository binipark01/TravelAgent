from __future__ import annotations

from fastapi import APIRouter

from travel_agent.app.config import get_settings
from travel_agent.app.sources.registry import SourceRegistry, SourceStatus

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("/status")
def provider_status() -> list[SourceStatus]:
    return SourceRegistry(get_settings()).all_status()
