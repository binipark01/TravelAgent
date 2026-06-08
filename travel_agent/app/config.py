from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv() -> None:
    env_path = Path(".env")
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def _list_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if value is None:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./travel_agent.db")
    )
    openai_api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY") or None)
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    codex_cli_command: str = field(default_factory=lambda: os.getenv("CODEX_CLI_COMMAND", "codex"))
    codex_oauth_model: str | None = field(
        default_factory=lambda: os.getenv("CODEX_OAUTH_MODEL", "gpt-5.5") or None
    )
    codex_oauth_timeout_seconds: int = field(
        default_factory=lambda: _int_env("CODEX_OAUTH_TIMEOUT_SECONDS", 240)
    )
    codex_oauth_enable_web_search: bool = field(
        default_factory=lambda: _bool_env("CODEX_OAUTH_ENABLE_WEB_SEARCH", True)
    )
    codex_reasoning_effort: str = field(
        default_factory=lambda: os.getenv("CODEX_REASONING_EFFORT", "low")
    )
    enable_flight_source_probes: bool = field(
        default_factory=lambda: _bool_env("ENABLE_FLIGHT_SOURCE_PROBES", True)
    )
    flight_source_probe_timeout_seconds: int = field(
        default_factory=lambda: _int_env("FLIGHT_SOURCE_PROBE_TIMEOUT_SECONDS", 12)
    )
    enable_live_llm: bool = field(default_factory=lambda: _bool_env("ENABLE_LIVE_LLM", False))
    enable_live_providers: bool = field(
        default_factory=lambda: _bool_env("ENABLE_LIVE_PROVIDERS", False)
    )
    provider_fallback_to_mock: bool = field(
        default_factory=lambda: _bool_env("PROVIDER_FALLBACK_TO_MOCK", True)
    )
    flight_sources: tuple[str, ...] = field(
        default_factory=lambda: _list_env(
            "FLIGHT_SOURCES", ("amadeus", "skyscanner", "naver_flight", "mock")
        )
    )
    accommodation_sources: tuple[str, ...] = field(
        default_factory=lambda: _list_env(
            "ACCOMMODATION_SOURCES",
            (
                "expedia_rapid",
                "hotelbeds",
                "booking_demand",
                "agoda_partner",
                "google_hotels_partner",
                "airbnb_public_page",
                "mock",
            ),
        )
    )
    poi_sources: tuple[str, ...] = field(
        default_factory=lambda: _list_env(
            "POI_SOURCES", ("google_places", "kakao_local", "kto_tourapi", "mock")
        )
    )
    route_sources: tuple[str, ...] = field(
        default_factory=lambda: _list_env(
            "ROUTE_SOURCES", ("google_routes", "naver_directions", "kakao_mobility", "mock")
        )
    )
    activity_sources: tuple[str, ...] = field(
        default_factory=lambda: _list_env("ACTIVITY_SOURCES", ("viator", "getyourguide", "mock"))
    )
    visa_sources: tuple[str, ...] = field(
        default_factory=lambda: _list_env("VISA_SOURCES", ("sherpa", "timatic", "mock"))
    )
    safety_sources: tuple[str, ...] = field(
        default_factory=lambda: _list_env("SAFETY_SOURCES", ("mofa", "mock"))
    )
    weather_sources: tuple[str, ...] = field(
        default_factory=lambda: _list_env("WEATHER_SOURCES", ("open_meteo", "openweather", "mock"))
    )
    fx_sources: tuple[str, ...] = field(
        default_factory=lambda: _list_env(
            "FX_SOURCES", ("frankfurter", "open_exchange_rates", "mock")
        )
    )
    default_locale: str = field(default_factory=lambda: os.getenv("DEFAULT_LOCALE", "ko-KR"))
    default_currency: str = field(default_factory=lambda: os.getenv("DEFAULT_CURRENCY", "KRW"))
    default_timezone: str = field(
        default_factory=lambda: os.getenv("DEFAULT_TIMEZONE", "Asia/Seoul")
    )
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: _list_env(
            "CORS_ORIGINS",
            (
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:5174",
                "http://127.0.0.1:5174",
            ),
        )
    )


# 런타임에 UI에서 변경할 수 있는 설정 override (프로세스 메모리, 재시작 시 초기화).
_RUNTIME_OVERRIDES: dict[str, object] = {}
_REASONING_EFFORTS = ("minimal", "low", "medium", "high")


def get_settings() -> Settings:
    return Settings(**_RUNTIME_OVERRIDES)


def runtime_settings_view() -> dict[str, object]:
    settings = get_settings()
    return {
        "enable_live_llm": settings.enable_live_llm,
        "enable_flight_source_probes": settings.enable_flight_source_probes,
        "codex_reasoning_effort": settings.codex_reasoning_effort,
    }


def apply_runtime_overrides(values: dict[str, object]) -> dict[str, object]:
    if "enable_live_llm" in values and values["enable_live_llm"] is not None:
        _RUNTIME_OVERRIDES["enable_live_llm"] = bool(values["enable_live_llm"])
    if (
        "enable_flight_source_probes" in values
        and values["enable_flight_source_probes"] is not None
    ):
        _RUNTIME_OVERRIDES["enable_flight_source_probes"] = bool(
            values["enable_flight_source_probes"]
        )
    effort = values.get("codex_reasoning_effort")
    if isinstance(effort, str) and effort in _REASONING_EFFORTS:
        _RUNTIME_OVERRIDES["codex_reasoning_effort"] = effort
    return runtime_settings_view()
