"""도시/국가명을 LLM(Codex)으로 공항코드·국가로 해석하는 best-effort 리졸버.

하드코딩 카탈로그(공항코드·도시→국가)에 없는 임의의 도시(시즈오카·구마모토 등)도
라이브 LLM이 켜져 있으면 여기서 해석한다. LLM이 꺼져 있거나 실패하면 None을 돌려주어
호출부가 기존 카탈로그/보수적 폴백을 그대로 쓰게 한다(오프라인 테스트 영향 없음).

국가/공항코드는 '지어내면 안 되는 라이브 사실'이 아니라 보편 지리 지식이므로 LLM 해석이
안전하다. 같은 프로세스 안에서 같은 지명은 한 번만 LLM에 묻고 캐시한다.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from travel_agent.app.agents.llm_client import live_llm_local_enabled, run_codex_json
from travel_agent.app.config import get_settings


@dataclass(frozen=True)
class ResolvedPlace:
    """LLM이 해석한 한 지명의 국가·대표 공항 정보."""

    country_ko: str | None
    iata: str | None
    skyscanner: str | None
    hub_note: str | None


_PROMPT = (
    "너는 여행 도시/공항 정보 리졸버다. 아래 장소(도시 또는 국가, 한국어/영어)에 대해 "
    "JSON 객체 하나만 출력하라. 설명·코드펜스 금지.\n"
    "{\n"
    '  "country_ko": "그 장소가 속한 국가의 한국어 이름(예: 일본, 태국, 미국, 프랑스, 베트남)",\n'
    '  "iata": "그 도시를 담당하는 주요 국제공항 IATA 3레터 코드. 도시 자체에 국제선이 '
    '거의 없으면 가장 가까운 허브 공항 코드",\n'
    '  "skyscanner": "그 도시/공항의 스카이스캐너 코드(소문자). 모르면 iata를 소문자로",\n'
    '  "hub_note": "iata가 그 도시가 아니라 인근 허브일 때만 한국어 한 문장 안내'
    "(예: 시즈오카는 국제선 직항이 적어 나고야(NGO) 도착 후 신칸센 이동 추천). 도시 자체 "
    '국제공항이면 null"\n'
    "}\n"
    "지명을 전혀 모르면 모든 값을 null로. iata는 실제 존재하는 공항 코드만 적는다.\n"
    "장소: "
)

# 같은 프로세스에서 같은 지명을 반복 조회하지 않도록 캐시(성공/실패 모두 기억).
# 비자·FX·안전·항공이 동시에 resolve_place를 부를 수 있어 락으로 dict race를 닫는다.
_CACHE: dict[str, ResolvedPlace | None] = {}
_CACHE_LOCK = threading.Lock()


def _normalize(name: str) -> str:
    return name.split(",")[0].strip().lower()


def _clean_str(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _valid_iata(code: str) -> bool:
    return len(code) == 3 and code.isalpha()


def _llm_resolve(name: str) -> ResolvedPlace | None:
    settings = get_settings()
    # 공항코드·국가는 보편 지리지식이라 웹검색 불필요 → 로컬 게이트.
    if not live_llm_local_enabled(settings):
        return None
    data = run_codex_json(
        _PROMPT + name,
        command=settings.codex_cli_command,
        model=settings.codex_oauth_model,
        reasoning_effort=settings.codex_reasoning_effort,
        timeout_seconds=60,
    )
    if not isinstance(data, dict):
        return None

    iata = _clean_str(data.get("iata"))
    iata = iata.upper() if iata else None
    if iata is not None and not _valid_iata(iata):
        iata = None
    country = _clean_str(data.get("country_ko"))
    if not country and not iata:
        return None
    sky = _clean_str(data.get("skyscanner"))
    sky = sky.lower() if sky else (iata.lower() if iata else None)
    return ResolvedPlace(
        country_ko=country,
        iata=iata,
        skyscanner=sky,
        hub_note=_clean_str(data.get("hub_note")),
    )


def resolve_place(name: str | None) -> ResolvedPlace | None:
    """지명 → ResolvedPlace. LLM이 꺼져 있거나 실패하면 None. 같은 지명은 캐시한다."""
    if not name or not name.strip():
        return None
    key = _normalize(name)
    # 캐시는 None(=해석 실패)도 의미 있게 기억하므로 멤버십(in)으로 확인한다.
    # read/write만 락으로 보호하고 LLM 호출은 락 밖에서 한다(같은 키 동시 cold-miss는
    # 드물게 중복 호출될 수 있으나 결과는 동일).
    with _CACHE_LOCK:
        if key in _CACHE:
            return _CACHE[key]
    resolved = _llm_resolve(name)
    with _CACHE_LOCK:
        _CACHE[key] = resolved
    return resolved


def clear_cache() -> None:
    """테스트용: 해석 캐시를 비운다."""
    with _CACHE_LOCK:
        _CACHE.clear()
