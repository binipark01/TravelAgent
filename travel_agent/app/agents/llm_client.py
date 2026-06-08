from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol
from urllib import request

from pydantic import ValidationError

from travel_agent.app.schemas.brief import TripBrief


def _coerce_traveler_count(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, dict):
        count = value.get("count") or value.get("value")
        return int(count) if isinstance(count, int | float) else None
    if isinstance(value, list):
        total = 0
        for item in value:
            if isinstance(item, dict):
                count = item.get("count") or item.get("value") or 1
                total += int(count) if isinstance(count, int | float) else 1
            elif isinstance(item, int | float) and not isinstance(item, bool):
                total += int(item)
        return total or None
    return None


def coerce_trip_brief(data: dict, currency: str) -> TripBrief:
    """LLM이 준 brief dict를 스키마에 맞게 보정한다.

    인원을 정수로 강제하고, 검증에 실패하는 필드는 떨어뜨려(기본값 사용) 전체가
    깨지지 않게 한다. LLM의 사소한 형식 일탈로 regex fallback에 빠지지 않도록 한다.
    """
    payload = {key: value for key, value in data.items() if value is not None}
    payload.setdefault("currency", currency)
    travelers = _coerce_traveler_count(payload.get("travelers"))
    if travelers is None:
        payload.pop("travelers", None)
    else:
        payload["travelers"] = travelers
    for _ in range(12):
        try:
            return TripBrief.model_validate(payload)
        except ValidationError as exc:
            bad = {str(error["loc"][0]) for error in exc.errors() if error.get("loc")}
            bad.discard("currency")
            if not bad:
                raise
            for field in bad:
                payload.pop(field, None)
    return TripBrief.model_validate(payload)


_SAFE_CODEX_ENV_KEYS = {
    "APPDATA",
    "CODEX_HOME",
    "COMSPEC",
    "HOME",
    "LOCALAPPDATA",
    "PATH",
    "PATHEXT",
    "SystemRoot",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "WINDIR",
}

_BRIEF_JSON_KEYS = (
    "origin, destination_hint, destinations, selected_destination, start_date, "
    "end_date, flexible_dates, duration_days, duration_nights, traveler_count, "
    "adults, children, travelers, budget_total, budget_per_person, currency, "
    "travel_style, pace, accommodation_preference, transport_preference, "
    "accessibility_needs, dietary_restrictions, passport_country, visa_status_known, "
    "must_include, must_avoid"
)


def codex_brief_available(command: str = "codex") -> bool:
    """True if the Codex CLI can be resolved on PATH."""
    candidates = (
        [f"{command}.cmd", f"{command}.exe", command] if os.name == "nt" else [command]
    )
    return any(shutil.which(candidate) for candidate in candidates)


class LLMClient(Protocol):
    def extract_trip_brief(
        self, message: str, currency: str, history: list[str] | None = None
    ) -> TripBrief: ...


class StubLLMClient:
    def extract_trip_brief(
        self, message: str, currency: str, history: list[str] | None = None
    ) -> TripBrief:
        raise RuntimeError("Live LLM is disabled; use deterministic intake fallback.")


class OpenAITripBriefClient:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def extract_trip_brief(
        self, message: str, currency: str, history: list[str] | None = None
    ) -> TripBrief:
        prior = [m for m in (history or []) if m and m.strip()][-6:]
        context_block = ""
        if prior:
            context_block = "이전 대화:\n" + "\n".join(f"- {m}" for m in prior) + "\n\n"
        json_keys = (
            "origin, destination_hint, destinations, selected_destination, start_date, "
            "end_date, flexible_dates, duration_days, duration_nights, traveler_count, "
            "adults, children, budget_total, budget_per_person, currency, travel_style, "
            "pace, accommodation_preference, transport_preference, accessibility_needs, "
            "dietary_restrictions, passport_country, visa_status_known, must_include, "
            "must_avoid, assumptions"
        )
        payload = {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "Extract an overseas travel planning brief from Korean or English natural "
                        "language. Return only compact JSON. Do not invent live facts, prices, "
                        "availability, opening hours, or visa rules."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Currency: {currency}\n"
                        f"{context_block}"
                        f"User request:\n{message}\n\n"
                        f"Return JSON keys: {json_keys}. Use ISO dates or null."
                    ),
                },
            ],
            "text": {"format": {"type": "json_object"}},
        }
        http_request = request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with request.urlopen(http_request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
        text = self._extract_text(body)
        data = json.loads(text)
        return coerce_trip_brief(data, currency)

    def _extract_text(self, body: dict) -> str:
        if body.get("output_text"):
            return body["output_text"]
        chunks: list[str] = []
        for item in body.get("output", []):
            for content in item.get("content", []):
                if "text" in content:
                    chunks.append(content["text"])
        if not chunks:
            raise RuntimeError("OpenAI response did not include extractable JSON text.")
        return "".join(chunks)


class CodexTripBriefClient:
    """Extract a TripBrief from natural language via the local Codex CLI (no API key needed)."""

    def __init__(
        self,
        *,
        command: str = "codex",
        model: str | None = "gpt-5.5",
        timeout_seconds: int = 90,
        reasoning_effort: str | None = None,
    ) -> None:
        self.command = command
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.reasoning_effort = reasoning_effort

    def extract_trip_brief(
        self, message: str, currency: str, history: list[str] | None = None
    ) -> TripBrief:
        context_block = ""
        prior = [m for m in (history or []) if m and m.strip()][-6:]
        if prior:
            joined = "\n".join(f"- {m.strip()}" for m in prior)
            context_block = (
                "아래는 같은 사용자와의 이전 요청들(과거→최근 순)이다. 최신 요청을 해석할 때 "
                "참고하라. 이전에 정해진 목적지·날짜·인원·예산은 최신 요청이 명시적으로 바꾸지 "
                "않는 한 그대로 유지하고, '거기'·'그때'·'추가로' 같은 표현은 "
                "이전 문맥으로 해석하라.\n"
                f"[이전 대화]\n{joined}\n\n"
            )
        prompt = (
            "다음 여행 요청에서 해외여행 계획 brief를 추출해 compact JSON 객체 하나만 출력하라. "
            "설명 문장이나 코드펜스 없이 순수 JSON만 출력한다. 모르는 값은 null로 둔다. "
            "사용자가 목적지/날짜/인원을 명시하지 않았으면 "
            "문맥상 가장 합리적인 값을 추정해서 채운다. "
            "단, 실제 가격/좌석/항공편 번호/비자 규칙은 지어내지 마라. 날짜는 ISO(YYYY-MM-DD).\n"
            f"통화: {currency}\n"
            f"JSON 키: {_BRIEF_JSON_KEYS}\n\n"
            f"{context_block}"
            f"[최신 요청]\n{message}"
        )
        with tempfile.TemporaryDirectory(prefix="travel-agent-brief-") as workdir:
            args = self._build_command(workdir)
            try:
                result = subprocess.run(
                    args,
                    input=prompt,
                    env=self._subprocess_env(),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except FileNotFoundError as exc:
                raise RuntimeError("Codex CLI를 찾지 못했습니다.") from exc
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("Codex brief 추출 시간이 초과되었습니다.") from exc

        text = self._extract_message(result.stdout)
        if not text:
            detail = result.stderr.strip() or f"exit code {result.returncode}"
            raise RuntimeError(f"Codex brief 응답을 읽지 못했습니다: {detail}")
        data = self._parse_json_object(text)
        return coerce_trip_brief(data, currency)

    def _build_command(self, workdir: str) -> list[str]:
        args = [self._resolve_command(), "-s", "read-only", "-a", "never", "-C", workdir]
        if self.model:
            args.extend(["-m", self.model])
        if self.reasoning_effort:
            args.extend(["-c", f"model_reasoning_effort={self.reasoning_effort}"])
        args.extend(
            [
                "exec",
                "-",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--skip-git-repo-check",
                "--json",
                "--color",
                "never",
            ]
        )
        return args

    def _subprocess_env(self) -> dict[str, str]:
        return {
            key: value
            for key in _SAFE_CODEX_ENV_KEYS
            if (value := os.environ.get(key)) is not None
        }

    def _resolve_command(self) -> str:
        command_path = Path(self.command)
        if command_path.suffix or command_path.parent != Path("."):
            return self.command
        candidates = (
            [f"{self.command}.cmd", f"{self.command}.exe", self.command]
            if os.name == "nt"
            else [self.command]
        )
        for candidate in candidates:
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
        return self.command

    def _extract_message(self, stdout: str) -> str:
        messages: list[str] = []
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "item.completed":
                continue
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    messages.append(text.strip())
        return "\n\n".join(messages).strip()

    def _parse_json_object(self, text: str) -> dict:
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        candidate = fenced.group(1) if fenced else text
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError("Codex 응답에서 JSON 객체를 찾지 못했습니다.")
        return json.loads(candidate[start : end + 1])
