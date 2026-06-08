from __future__ import annotations

from fastapi import APIRouter

from travel_agent.app.config import apply_runtime_overrides, runtime_settings_view
from travel_agent.app.schemas.common import StrictBaseModel

router = APIRouter(prefix="/settings", tags=["settings"])


class RuntimeSettings(StrictBaseModel):
    enable_live_llm: bool
    enable_flight_source_probes: bool
    codex_reasoning_effort: str


class RuntimeSettingsUpdate(StrictBaseModel):
    enable_live_llm: bool | None = None
    enable_flight_source_probes: bool | None = None
    codex_reasoning_effort: str | None = None


@router.get("", response_model=RuntimeSettings)
def read_runtime_settings() -> RuntimeSettings:
    return RuntimeSettings(**runtime_settings_view())


@router.post("", response_model=RuntimeSettings)
def update_runtime_settings(payload: RuntimeSettingsUpdate) -> RuntimeSettings:
    updated = apply_runtime_overrides(payload.model_dump())
    return RuntimeSettings(**updated)
