---
name: travelagent-dev
description: "TravelAgent(증거기반 멀티에이전트 여행 플래너) 개발 작업을 조율하는 오케스트레이터. 기능 추가·버그 수정·리팩터·품질 개선이 백엔드(Python/FastAPI)·프론트(React)·LLM 프롬프트에 걸칠 때, backend-engineer/frontend-engineer/qa-verifier 팀을 구성해 구현→검증→보고까지 끌고 간다. 'TravelAgent 기능/버그/일정/지도/추천 ~해줘', '풀스택으로', '다시/재실행/업데이트/수정/보완/개선', '이전 결과 기반으로' 요청 시 반드시 사용. 단순 질문은 직접 응답."
---

# TravelAgent Dev — 개발 오케스트레이터

TravelAgent 개발 요청을 받아 전문 에이전트 팀(backend·frontend·qa)을 조율한다. 누가 무엇을 하는지는 각 에이전트/스킬이, **누가 언제 어떤 순서로 협업하는지**는 이 스킬이 정한다.

**실행 모드:** 에이전트 팀(기본). `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`이 없으면 팀이 단일 에이전트로 폴백하므로, 그 경우 아래 "서브 에이전트 폴백"으로 전환한다. 모든 Agent 호출은 `model: "opus"`.

## Phase 0: 컨텍스트 확인
1. `_workspace/` 존재 + **부분 수정** 요청 → 해당 에이전트만 재호출(부분 재실행).
2. `_workspace/` 존재 + **새 입력** → 기존을 `_workspace_prev/`로 옮기고 새 실행.
3. `_workspace/` 없음 → 초기 실행.
4. 단순 질문(코드 위치·설명)이면 팀 없이 직접 답한다.

## Phase 1: 분류
요청을 영역으로 나눈다:
- **백엔드만** — app/agents·llm·schemas·api → backend-engineer
- **프론트만** — components·types → frontend-engineer
- **프롬프트 품질** — 추천/동선/곳수/시간대 → backend-engineer(`llm-prompt-tuning`)
- **풀스택** — 응답 shape + UI 둘 다(예: 지도/동선, 새 카드) → 두 엔지니어 + 경계면 통지
- 어느 경우든 변경 후 **qa-verifier 필수**.

## Phase 2: 팀 구성 & 실행 (에이전트 팀 — 기본)
```
TeamCreate(team="travelagent-dev", members=[backend-engineer, frontend-engineer, qa-verifier])
TaskCreate(작업들 + 의존성)   # 예: BE 변경 → (shape 통지) → FE 변경 → QA 경계면 검증
팀원은 SendMessage로 자체 조율:
  - backend-engineer: 응답 shape 바꾸면 즉시 frontend-engineer·qa-verifier에 통지
  - frontend-engineer: 기대 shape을 backend-engineer에 확인
  - qa-verifier: 경계면 불일치 발견 시 해당 엔지니어에 즉시 통지
리더(오케스트레이터): 진행 모니터링 → 결과 종합 → 팀 정리
```
풀스택이 아니면 필요한 멤버만(예: 프롬프트 작업 = backend + qa 2명).

### 서브 에이전트 폴백 (플래그 없을 때)
`Agent` 도구로 직접 호출(`model: "opus"`). 독립 작업은 `run_in_background: true`로 병렬, 결과는 파일(`_workspace/`)로 주고받는다. 경계면 통지가 자동으로 안 되므로 **오케스트레이터가 BE 산출물의 shape 변경을 FE/QA에 명시적으로 전달**한다.

## Phase 3: 데이터 전달 프로토콜
- **태스크 기반**(조율): `TaskCreate`/`TaskUpdate`로 의존·진행 추적.
- **파일 기반**(산출물): `_workspace/{phase}_{agent}_{artifact}.md` (예: `01_backend_schema.md`). 중간 파일 보존(감사용), 최종 코드만 레포에.
- **메시지 기반**(실시간): 경계면 변경·확인은 `SendMessage`.

## Phase 4: 검증 게이트
qa-verifier가 `live-verify`로: pytest + ruff + npm build + (LLM/통합 변경이면) 라이브 API 프로브 + 경계면 교차 비교. **PASS 못 하면 완료 아님.** LLM 프롬프트 변경은 오프라인 테스트로 안 잡히니 라이브 프로브 필수.

## Phase 5: 보고 & 커밋 게이트
- 변경 파일·핵심 diff·검증 결과(테스트/프로브/스크린샷)를 사용자에게 보고.
- **커밋은 사용자 흐름을 따른다** — 이 레포 관례는 구현→검증→커밋·푸시이나, 커밋 메시지는 한국어 본문 + `Co-Authored-By: Claude Opus 4.8`. 사용자가 멈추라 하면 멈춘다.

## 에러 핸들링
- 엔지니어/QA 작업 1회 재시도 후 재실패면 그 결과 없이 진행하되 **보고서에 누락·실패를 명시**(통과처럼 보고 금지).
- 상충 데이터(예: 두 검증 결과 불일치)는 삭제 말고 출처 병기.
- 경계면 불일치는 코드 우회가 아니라 어느 쪽이 맞는지 정해 양쪽을 일치시킨다.

## 후속 작업
"다시/재실행/수정/보완/개선/이전 결과 기반" 요청은 Phase 0의 부분 재실행으로 처리한다. 매 실행 후 사용자에게 개선점을 물어 하네스(에이전트/스킬/`AGENTS.md`)에 반영한다.

## 테스트 시나리오
- **정상 흐름(풀스택)**: "지도 동선이 숙소에서 출발 안 해" → 분류=풀스택 → BE(arranger 프롬프트에 숙소 bookend) + FE(PlanCards 동선 anchor) → QA(라이브 프로브로 day별 첫/끝 stop=숙소 확인 + 빌드) → 보고 → 커밋. 기대: 모든 날 숙소→…→숙소.
- **에러 흐름**: QA가 경계면 불일치(백엔드 새 필드를 프론트가 안 읽음) 발견 → 해당 엔지니어에 통지 → 1회 수정 → 재검증. 재실패면 누락 명시하고 사용자에 보고.
