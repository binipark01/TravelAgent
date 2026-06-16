"""코어 오케스트레이터 플래너.

사용자 요청과 intake brief를 보고, 실제로 필요한 서브에이전트(capability)만 골라
실행 계획을 만든다. 가용한 LLM(Codex)이 있으면 LLM이 판단하고, 없거나 실패하면
규칙 기반(fallback)으로 선택한다. 어떤 경우에도 계획은 항상 반환된다.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# 코어가 디스패치할 수 있는 서브에이전트(capability) 카탈로그.
CAPABILITIES: dict[str, str] = {
    "flight": "항공권/이동 후보 검색 (출발지·목적지·날짜·인원 기반)",
    "accommodation": "숙소 후보 검색 (목적지·체크인/아웃 기반)",
    "restaurant": "맛집·식당(및 쇼핑·관광·체험) 장소 후보 탐색",
    "route": "일자별 동선/일정 최적화 (장소 후보 필요)",
    "budget": "예상 비용/예산 계산",
}

# 실행 시 의존성 안전 순서.
CAPABILITY_ORDER: list[str] = ["flight", "accommodation", "restaurant", "route", "budget"]

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


@dataclass(frozen=True)
class CorePlan:
    agents: list[str]
    reason: str
    source: str  # "llm" | "fallback"


class CorePlannerAgent:
    def __init__(
        self,
        *,
        command: str = "codex",
        model: str | None = "gpt-5.5",
        timeout_seconds: int = 60,
        enabled: bool = False,
        reasoning_effort: str | None = None,
    ) -> None:
        self.command = command
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.enabled = enabled
        self.reasoning_effort = reasoning_effort

    def plan(self, state: Any) -> CorePlan:
        brief = getattr(state, "brief", None)
        request_text = getattr(state, "raw_user_message", "") or ""
        # 명확한 단일 도메인 요청('항공권 찾아줘' 등)은 LLM의 과한 확장을 막고 좁게 확정한다.
        focused = self._focused_plan(brief, request_text)
        if focused is not None:
            return focused
        if self.enabled:
            try:
                agents, reason = self._llm_select(brief, request_text)
                ordered = [key for key in CAPABILITY_ORDER if key in set(agents)]
                if ordered:
                    return CorePlan(agents=ordered, reason=reason or "코어 LLM 판단", source="llm")
            except Exception as exc:  # LLM 실패 시 규칙 기반으로 폴백
                fallback = self._fallback(brief, request_text)
                return CorePlan(
                    agents=fallback.agents,
                    reason=f"LLM 계획 실패로 규칙 기반 선택: {exc}",
                    source="fallback",
                )
        return self._fallback(brief, request_text)

    # ------------------------------------------------------------------ LLM
    def _llm_select(self, brief: Any, request_text: str) -> tuple[list[str], str]:
        catalog = "\n".join(f"- {key}: {desc}" for key, desc in CAPABILITIES.items())
        brief_summary = self._brief_summary(brief)
        prompt = (
            "너는 여행 플래닝 시스템의 코어 오케스트레이터다. 사용자 요청과 분석된 brief를 "
            "보고, 아래 서브에이전트(capability) 중 이번 요청에 실제로 필요한 것만 골라라.\n\n"
            f"[사용 가능한 서브에이전트]\n{catalog}\n\n"
            f"[분석된 brief]\n{brief_summary}\n\n"
            f"[사용자 요청]\n{request_text}\n\n"
            "규칙:\n"
            "- 설명/코드펜스 없이 JSON 객체 하나만 출력한다.\n"
            '- 형식: {"agents": ["flight", ...], "reason": "한국어 한 줄 사유"}\n'
            "- agents 값은 위 키 중에서만 고른다.\n"
            "- '항공권만/비행기만' 요청이면 [\"flight\"]처럼 최소한만 고른다.\n"
            "- '호텔/숙소만' 요청이면 [\"accommodation\"].\n"
            "- '일정/코스/여행 계획' 같은 종합 요청이면 필요한 것을 폭넓게 고른다.\n"
            "- 동선/일정 최적화(route)를 고르면 restaurant도 함께 고른다.\n"
        )
        data = self._run_codex(prompt)
        agents = data.get("agents") or []
        if not isinstance(agents, list):
            agents = []
        agents = [str(item).strip().lower() for item in agents if str(item).strip()]
        reason = str(data.get("reason") or "").strip()
        return agents, reason

    def _brief_summary(self, brief: Any) -> str:
        if brief is None:
            return "(brief 없음)"
        parts = [
            f"목적지: {', '.join(getattr(brief, 'destinations', []) or []) or '미정'}",
            f"출발지: {getattr(brief, 'origin', None) or '미정'}",
            f"인원: {getattr(brief, 'travelers', None) or '미정'}",
            f"교통선호: {getattr(brief, 'transport_preference', None) or '없음'}",
            f"숙소선호: {getattr(brief, 'accommodation_preference', None) or '없음'}",
            f"관심사: {', '.join(getattr(brief, 'must_include', []) or []) or '없음'}",
        ]
        return "\n".join(parts)

    def _run_codex(self, prompt: str) -> dict:
        with tempfile.TemporaryDirectory(prefix="travel-agent-plan-") as workdir:
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
                raise RuntimeError("코어 플래너 LLM 응답 시간이 초과되었습니다.") from exc
        text = self._extract_message(result.stdout)
        if not text:
            detail = result.stderr.strip() or f"exit code {result.returncode}"
            raise RuntimeError(f"코어 플래너 응답을 읽지 못했습니다: {detail}")
        return self._parse_json_object(text)

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
            raise RuntimeError("코어 플래너 응답에서 JSON 객체를 찾지 못했습니다.")
        return json.loads(candidate[start : end + 1])

    # --------------------------------------------------------- focused scope
    _FULL_PLAN_TOKENS = (
        "일정", "여행 계획", "여행계획", "코스", "동선", "플랜",
        "계획 짜", "계획짜", "다 짜", "전부", "한바퀴", "스케줄",
    )

    def _focused_plan(self, brief: Any, request_text: str) -> CorePlan | None:
        """단일 도메인(항공/숙소/맛집)만 원하는 요청이면 그것만 고른다. 종합 키워드가
        있으면 None을 반환해 LLM/규칙이 폭넓게 고르게 한다."""
        text = (request_text or "").lower()
        if any(token in text for token in self._FULL_PLAN_TOKENS):
            return None
        pref = (getattr(brief, "transport_preference", None) or "") if brief else ""
        is_flight = "flight_search" in pref or any(
            token in text for token in ("항공권", "비행기", "항공편", "flight")
        )
        wants_hotel = any(
            token in text for token in ("숙소", "호텔", "에어비앤비", "airbnb", "아고다", "agoda")
        )
        # 맛집/쇼핑/관광은 '종합 여행의 관심사'로 더 많이 쓰여 단일 도메인 판정에서 제외하고,
        # 다른 도메인 신호로만 본다(예: '맛집이랑 쇼핑 위주'는 종합 계획이지 맛집검색이 아님).
        other_interest = any(
            token in text for token in ("맛집", "식당", "레스토랑", "쇼핑", "관광", "코스")
        )
        if is_flight and not wants_hotel and not other_interest:
            return CorePlan(["flight"], "항공권 검색 요청(단일 도메인)", "rule")
        if wants_hotel and not is_flight and not other_interest:
            return CorePlan(["accommodation"], "숙소 검색 요청(단일 도메인)", "rule")
        return None

    # ------------------------------------------------------------- fallback
    def _fallback(self, brief: Any, request_text: str) -> CorePlan:
        text = (request_text or "").lower()
        pref = (getattr(brief, "transport_preference", None) or "") if brief else ""
        is_flight_only = "flight_search" in pref or any(
            token in text for token in ["항공권만", "비행기만", "항공권 만"]
        )
        wants_accommodation = any(
            token in text
            for token in ["숙소", "호텔", "에어비앤비", "airbnb", "agoda", "booking.com"]
        )
        wants_full_plan = any(
            token in text
            for token in ["일정", "여행 계획", "여행계획", "동선", "맛집", "쇼핑", "관광", "코스"]
        )
        if is_flight_only:
            return CorePlan(["flight"], "항공권 검색 요청으로 판단", "fallback")
        if wants_accommodation and not wants_full_plan:
            return CorePlan(["accommodation"], "숙소 검색 요청으로 판단", "fallback")
        return CorePlan(
            ["flight", "accommodation", "restaurant", "route", "budget"],
            "종합 여행 계획 요청으로 판단",
            "fallback",
        )
