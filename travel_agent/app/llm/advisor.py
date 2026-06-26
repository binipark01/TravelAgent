"""항공·숙소 후보에 LLM이 '가성비/장단점 한 줄 평'을 다는 어드바이저.

항공·숙소는 가격·시간 같은 하드 데이터지만, "최저가지만 경유 길다", "역세권·평점 높은데
다소 비쌈" 같은 판단은 사람이 보고 싶어 한다. 후보 목록을 LLM에 주고 각 후보에 짧은 한 줄
평을 받아 옵션 notes에 💬로 붙인다. 웹검색은 필요 없다(주어진 후보만 판단).

라이브 LLM이 꺼져 있거나 실패하면 아무것도 안 붙인다(no-op) — 오프라인 테스트 영향 없음.
"""

from __future__ import annotations

from travel_agent.app.agents.llm_client import live_llm_local_enabled, run_codex_json
from travel_agent.app.config import get_settings
from travel_agent.app.schemas.providers import AccommodationOption, FlightOption


def estimate_daily_costs(
    destination: str, *, travel_style: str | None, currency: str
) -> tuple[int, int] | None:
    """목적지·스타일에 맞는 1인 1일 (식비, 현지교통) 추정. 비활성/실패 시 None.

    고정 6만/1.5만원은 유럽엔 너무 적고 동남아엔 너무 많다. 도시 물가를 LLM이 추정한다.
    """
    settings = get_settings()
    # 도시 물가 추정은 보편 지식이라 웹검색 불필요 → 로컬 게이트.
    if not live_llm_local_enabled(settings):
        return None
    style = travel_style or "보통"
    prompt = (
        f"'{destination}' 여행의 1인 1일 현지 경비를 {currency} 기준으로 추정하라. "
        f"여행 스타일은 '{style}'. 식비(세 끼+간식)와 현지교통(대중교통·근거리)만. "
        "항공·숙박·입장료는 제외. 그 도시 물가에 맞게 현실적으로.\n"
        '출력은 설명·코드펜스 없이 JSON 하나만: {"food": 정수, "local_transport": 정수}'
    )
    data = run_codex_json(
        prompt,
        command=settings.codex_cli_command,
        model=settings.codex_oauth_model,
        reasoning_effort=settings.codex_reasoning_effort,
        timeout_seconds=min(settings.codex_oauth_timeout_seconds, 60),
    )
    if not isinstance(data, dict):
        return None
    try:
        food = int(data["food"])
        transport = int(data["local_transport"])
    except (KeyError, TypeError, ValueError):
        return None
    if food <= 0 or transport <= 0:
        return None
    return food, transport


def _advise(items: list[tuple[str, str]], *, kind_label: str, context: str) -> dict[str, str]:
    """[(id, 설명)] → {id: 한 줄 평}. 비활성/실패 시 빈 dict."""
    if not items:
        return {}
    settings = get_settings()
    # 주어진 후보만 보고 한 줄 평을 다는 거라 웹검색 불필요 → 로컬 게이트.
    if not live_llm_local_enabled(settings):
        return {}
    lines = "\n".join(f"- [{item_id}] {text}" for item_id, text in items[:8])
    prompt = (
        f"너는 한국인 여행자를 돕는 상담원이다. 아래 {kind_label} 후보 각각에 대해 "
        "가성비·장단점·누구에게 맞는지를 고려한 짧은 한국어 한 줄 평(35자 내외)을 달아라. "
        "과장·허위 금지, 후보에 적힌 사실 범위에서만 평한다.\n"
        f"맥락: {context}\n"
        f"{lines}\n\n"
        '출력은 설명·코드펜스 없이 JSON 하나만: {"comments": {"후보ID": "한 줄 평", ...}}'
    )
    data = run_codex_json(
        prompt,
        command=settings.codex_cli_command,
        model=settings.codex_oauth_model,
        reasoning_effort=settings.codex_reasoning_effort,
        timeout_seconds=min(settings.codex_oauth_timeout_seconds, 90),
    )
    if not isinstance(data, dict):
        return {}
    comments = data.get("comments")
    if not isinstance(comments, dict):
        # 모델이 {id: 평} 형태로 바로 줄 수도 있다.
        comments = data
    result: dict[str, str] = {}
    for item_id, _ in items:
        value = comments.get(item_id)
        if isinstance(value, str) and value.strip():
            result[item_id] = value.strip()
    return result


def _won(amount: float | None) -> str:
    return f"{int(amount):,}원" if amount else "가격미상"


def _flight_desc(option: FlightOption) -> str:
    facts = [option.airline, _won(option.price.amount)]
    facts.extend(
        note for note in option.notes if note.startswith(("경유", "가는 편 소요", "오는 편 소요"))
    )
    return " · ".join(facts)


def _hotel_desc(option: AccommodationOption) -> str:
    parts = [option.name, f"{_won(option.nightly_price.amount)}/박"]
    if option.rating is not None:
        parts.append(f"평점 {option.rating:.1f}")
    if option.star_rating is not None:
        parts.append(f"{option.star_rating}성급")
    area = option.location.area
    if area:
        parts.append(area)
    return " · ".join(parts)


def advise_flights(options: list[FlightOption], *, context: str) -> None:
    """각 항공 후보의 notes 맨 앞에 💬 한 줄 평을 붙인다(가능할 때)."""
    comments = _advise(
        [(o.option_id, _flight_desc(o)) for o in options],
        kind_label="항공편",
        context=context,
    )
    for option in options:
        comment = comments.get(option.option_id)
        if comment:
            option.notes.insert(0, f"💬 {comment}")


def advise_hotels(options: list[AccommodationOption], *, context: str) -> None:
    """각 숙소 후보의 notes 맨 앞에 💬 한 줄 평을 붙인다(가능할 때)."""
    comments = _advise(
        [(o.option_id, _hotel_desc(o)) for o in options],
        kind_label="숙소",
        context=context,
    )
    for option in options:
        comment = comments.get(option.option_id)
        if comment:
            option.notes.insert(0, f"💬 {comment}")
