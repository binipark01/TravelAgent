# AGENTS.md

설명할 때 필수적인 용어 제외하고 한글로 작성하기.

이 저장소는 CRUD 앱이 아니라 agent-runtime 프로젝트입니다.

규칙:

- agents는 tool을 호출한다.
- tools는 connector를 호출한다.
- connectors는 provider/source output을 evidence로 normalize한다.
- final plan에는 raw provider data를 직접 넣지 않는다.
- mock data는 dev/test/fallback으로만 사용하고 live처럼 표시하지 않는다.
- 실제 결제, 발권, 예약, 취소, 이메일, calendar side effect 금지.
- booking simulation은 approval gate 뒤에서만 실행한다.
- tests는 live network를 호출하지 않는다.

## 하네스: TravelAgent 개발

**목표:** 백엔드(Python/FastAPI)·프론트(React)·LLM 프롬프트에 걸친 개발 작업을, 구현→검증(경계면·라이브)→보고까지 전문 에이전트 팀으로 일관되게 처리한다.

**트리거:** TravelAgent 기능 추가·버그 수정·일정/지도/추천 품질 개선 등 개발 요청 시 `travelagent-dev` 스킬을 사용하라(후속 "다시/재실행/수정/보완/개선" 포함). 단순 질문·코드 위치 설명은 직접 응답 가능.

**실행 의존성:** 에이전트 팀이 기본. `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` 미설정 시 단일 에이전트로 폴백(오케스트레이터가 서브 에이전트 모드로 전환).

**변경 이력:**
| 날짜 | 변경 내용 | 대상 | 사유 |
|------|----------|------|------|
| 2026-06-26 | 초기 구성(backend-engineer·frontend-engineer·qa-verifier + travelagent-dev 오케스트레이터 + backend-change·llm-prompt-tuning·frontend-change·live-verify 스킬) | 전체 | - |
