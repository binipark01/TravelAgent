from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from urllib import request
from zoneinfo import ZoneInfo

SAFE_CODEX_ENV_KEYS = {
    "APPDATA",
    "CODEX_HOME",
    "COMSPEC",
    "HOME",
    "LOCALAPPDATA",
    "PATH",
    "PATHEXT",
    "SystemRoot",
    "TEMP", "TMP",
    "USERPROFILE",
    "WINDIR",
}


def _travel_answer_instruction(
    *,
    locale: str,
    currency: str,
    timezone: str,
) -> str:
    return (
        "너는 사용자의 여행 요청에 바로 답하는 한국어 LLM 여행 상담원이다. "
        "사용자 입력을 파서나 워크스페이스로 넘겼다고 말하지 말고, 바로 답하라. "
        "항공권, 숙소, 예약 가능 여부처럼 실시간 가격/좌석이 필요한 요청은 "
        "확인된 후보를 우선 제시하라. 확인된 후보가 없으면 검색 방법을 답변처럼 "
        "포장하지 말고 후보 없음, 실패한 출처, 필요한 다음 실행을 짧게 말하라. "
        "모르는 실제 가격, 좌석, 항공편 번호는 지어내지 마라. "
        f"오늘 날짜는 {datetime.now(ZoneInfo(timezone)).date().isoformat()}, "
        f"사용 언어는 {locale}, 기본 통화는 {currency}다."
    )


# 계획/검색 요청이 아니라 '정보를 묻는 대화형 질문'인지 가르는 보수적 휴리스틱.
_PLAN_BUILD_TOKENS = (
    "계획", "일정 짜", "일정짜", "짜줘", "짜 줘", "예산", "예약해", "예약 해",
)
# 앱이 카드로 검색하는 도메인(이건 파이프라인이 카드로 답하게 둔다).
_DOMAIN_SEARCH_TOKENS = (
    "항공권", "비행기", "항공편", "숙소", "호텔", "맛집", "관광지", "렌트", "교통",
)
_QUESTION_TOKENS = (
    "뭐", "무엇", "볼거", "볼 거", "볼만", "볼 만", "명소", "구경", "가볼", "가 볼",
    "어때", "어떄", "어떨", "어디", "어떤", "어떻게", "왜", "궁금", "차이",
    "있나", "있냐", "있어?", "있을까", "알려", "?",
)


def is_conversational_question(message: str | None) -> bool:
    """계획/검색 요청이 아니라 정보를 묻는 대화형 질문이면 True(LLM이 바로 답하게).

    계획 수립(계획·예산·짜줘)이나 도메인 검색(항공/숙소/맛집 등)이 섞이면 파이프라인이
    카드로 답하도록 False. 순수 질문(볼거·명소·어때·뭐있냐 등)만 True.
    """
    text = (message or "").strip()
    if not text:
        return False
    if any(token in text for token in _PLAN_BUILD_TOKENS):
        return False
    if any(token in text for token in _DOMAIN_SEARCH_TOKENS):
        return False
    return any(token in text for token in _QUESTION_TOKENS)


def build_answer_client(settings) -> DirectLLMAnswerClient | CodexOAuthAnswerClient:  # noqa: F821
    """설정에 맞는 직답 LLM 클라이언트를 만든다(OpenAI 키 있으면 API, 없으면 Codex OAuth)."""
    if settings.openai_api_key:
        return DirectLLMAnswerClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            enable_web_search=settings.codex_oauth_enable_web_search,
        )
    return CodexOAuthAnswerClient(
        command=settings.codex_cli_command,
        model=settings.codex_oauth_model,
        timeout_seconds=settings.codex_oauth_timeout_seconds,
        enable_web_search=settings.codex_oauth_enable_web_search,
    )


class DirectLLMAnswerClient:
    def __init__(self, api_key: str, model: str, enable_web_search: bool = True) -> None:
        self.api_key = api_key
        self.model = model
        self.enable_web_search = enable_web_search

    def answer(
        self,
        *,
        message: str,
        locale: str = "ko-KR",
        currency: str = "KRW",
        timezone: str = "Asia/Seoul",
    ) -> str:
        payload = self._build_payload(
            message=message,
            locale=locale,
            currency=currency,
            timezone=timezone,
        )
        http_request = request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with request.urlopen(http_request, timeout=45) as response:
            body = json.loads(response.read().decode("utf-8"))
        return self._extract_text(body)

    def _build_payload(
        self,
        *,
        message: str,
        locale: str,
        currency: str,
        timezone: str,
    ) -> dict:
        system_prompt = _travel_answer_instruction(
            locale=locale,
            currency=currency,
            timezone=timezone,
        )
        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            "max_output_tokens": 900,
        }
        if self.enable_web_search:
            payload["tools"] = [{"type": "web_search_preview"}]
        return payload

    def _extract_text(self, body: dict) -> str:
        if body.get("output_text"):
            return str(body["output_text"]).strip()
        chunks: list[str] = []
        for item in body.get("output", []):
            for content in item.get("content", []):
                if "text" in content:
                    chunks.append(str(content["text"]))
        if not chunks:
            raise RuntimeError("LLM 응답에서 텍스트를 찾지 못했습니다.")
        return "".join(chunks).strip()


class CodexOAuthAnswerClient:
    def __init__(
        self,
        *,
        command: str = "codex",
        model: str | None = "gpt-5.5",
        timeout_seconds: int = 240,
        enable_web_search: bool = True,
    ) -> None:
        self.command = command
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.enable_web_search = enable_web_search

    def answer(
        self,
        *,
        message: str,
        locale: str = "ko-KR",
        currency: str = "KRW",
        timezone: str = "Asia/Seoul",
    ) -> str:
        prompt = self._build_prompt(
            message=message,
            locale=locale,
            currency=currency,
            timezone=timezone,
        )
        with tempfile.TemporaryDirectory(prefix="travel-agent-codex-") as workdir:
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
                raise RuntimeError("Codex OAuth LLM 응답 시간이 초과되었습니다.") from exc

        answer = self._extract_answer_from_jsonl(result.stdout)
        if answer:
            return answer
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        detail = stderr or stdout or f"exit code {result.returncode}"
        raise RuntimeError(f"Codex OAuth LLM 응답을 읽지 못했습니다: {detail}")

    def _build_command(self, workdir: str) -> list[str]:
        args = [
            self._resolve_command(),
            "-s",
            "read-only",
            "-a",
            "never",
            "-C",
            workdir,
        ]
        if self.model:
            args.extend(["-m", self.model])
        if self.enable_web_search:
            args.append("--search")
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
            for key in SAFE_CODEX_ENV_KEYS
            if (value := os.environ.get(key)) is not None
        }

    def _resolve_command(self) -> str:
        command_path = Path(self.command)
        if command_path.suffix or command_path.parent != Path("."):
            return self.command
        candidates = [self.command]
        if os.name == "nt":
            candidates = [f"{self.command}.cmd", f"{self.command}.exe", self.command]
        for candidate in candidates:
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
        return self.command

    def _build_prompt(
        self,
        *,
        message: str,
        locale: str,
        currency: str,
        timezone: str,
    ) -> str:
        instruction = _travel_answer_instruction(
            locale=locale,
            currency=currency,
            timezone=timezone,
        )
        return (
            f"{instruction}\n\n"
            "추가 실행 규칙:\n"
            "- 현재 가격, 운항 시간, 입국 조건, 영업시간처럼 변동 가능한 정보가 "
            "필요하면 live web search를 사용하라.\n"
            "- 파일, 터미널, 로컬 브라우저, shell 명령은 쓰지 마라. "
            "허용된 도구는 live web search뿐이다.\n"
            "- 검색한 정보와 출처를 바탕으로 답하고, 확인하지 못한 가격/좌석/편명은 "
            "지어내지 마라.\n"
            "- 항공권 후보를 실제로 확인하지 못했으면 날짜 변경 팁이나 일반론으로 "
            "답변을 채우지 말고 후보 없음과 필요한 다음 실행만 말하라.\n"
            "- 답변 끝에는 참고한 출처 이름과 URL을 짧게 적어라.\n"
            "- 코드베이스 분석이나 작업 계획을 하지 마라.\n"
            "- 사용자에게 보여줄 최종 답변만 작성하라.\n\n"
            f"사용자 요청:\n{message}"
        )

    def _extract_answer_from_jsonl(self, stdout: str) -> str:
        messages: list[str] = []
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "item.completed":
                continue
            item = event.get("item")
            if not isinstance(item, dict):
                continue
            if item.get("type") != "agent_message":
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                messages.append(text.strip())
        return "\n\n".join(messages).strip()
