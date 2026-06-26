---
name: backend-change
description: "TravelAgent 백엔드(Python/FastAPI) 코드를 추가·수정·리팩터·디버그할 때 사용. app/agents·app/llm·schemas·api·alembic 변경, 새 에이전트/큐레이터 배선, Pydantic 스키마 변경, ruff·pytest 통과까지. '백엔드 고쳐줘/추가해줘', '에이전트/스키마/API 수정', '다시/재실행/보완', '이 버그 백엔드 쪽' 요청 시 반드시 사용."
---

# Backend Change — TravelAgent Python 변경 절차

백엔드를 안전하게 바꾸기 위한 절차와 규약. 이 프로젝트는 증거기반 멀티에이전트 여행 플래너라, 규약을 어기면 라이브 LLM·테스트·프론트 정합성이 조용히 깨진다.

## 1. 변경 전 파악
- 멀티에이전트 흐름: `app/agents/supervisor.py`가 코어/크로스커팅 wave로 에이전트를 돌린다. 새 에이전트는 supervisor 배선 + 상태(`schemas/trip.py`) 추가가 함께다.
- LLM 계층: `app/llm/curator.py`(관광지·식당·근교·숙박구역·이벤트·동반도시), `itinerary_arranger.py`(일정 배치 + 커뮤니티 코스), `advisor.py`, `source_guide.py`, `geo_resolver.py`.
- 호출 게이트: `run_codex_json(..., enable_web_search=)`는 `enable_live_llm`+`codex_oauth_enable_web_search`+codex 가용성으로 게이트(`_enabled()`). 오프라인 테스트는 전부 off → 휴리스틱 폴백.

## 2. 변경 원칙 (why 포함)
- **스키마는 StrictBaseModel** — 임의 필드 금지. 응답 shape을 바꾸면 프론트가 깨지니, 변경 사실을 frontend-engineer/qa-verifier에 알린다.
- **결정적 값은 코드, 도시별 지식은 LLM** — 예: 동선 좌표·이동수단은 코드, 공항 정확한 이름(오사카=간사이≠이타미)은 LLM.
- **LLM 새 호출도 게이트를 탄다** — `_enabled()`/`settings` 체크 없이 LLM을 부르면 오프라인 테스트가 깨진다.
- **스레드 안전** — recorder/SQLAlchemy 비안전. 병렬은 ThreadPoolExecutor로 액션만, step 기록은 메인스레드(supervisor `_run_parallel` 패턴).
- **이유를 주석으로** — anchor·게이팅·폴백 같은 비자명 결정은 why를 남긴다.

## 3. 검증 (필수, 순서대로)
```bash
python -m ruff check <changed files>          # line 100, I001
python -m pytest tests/ -p no:cacheprovider -q # 전체 통과
```
- ruff 실패: 줄바꿈/`ruff --fix`. 한글 문자열 길이 주의.
- LLM 경로 변경은 오프라인 테스트로 안 잡힌다 → qa-verifier의 라이브 프로브로 확인(`live-verify`).

## 4. 서버 반영
Python은 핫리로드 없음. 백엔드 변경은 재시작 필요:
```powershell
./stop_servers.ps1; ./start_servers.ps1   # 백엔드 8000 / 프론트 5173
```
캐시(`_COMMUNITY_COURSE_CACHE` 등)는 메모리라 재시작 시 비워진다.

## 5. 프롬프트 변경이면
큐레이터/배치기 프롬프트 수정은 `llm-prompt-tuning` 스킬을 함께 본다(게이트·라이브 검증 방식이 다름).

## 마무리
변경 파일·diff 요약·ruff/pytest 결과를 보고하고, 프론트 영향이 있으면 명시한다. 커밋은 오케스트레이터가 게이트한다(사용자 승인 흐름).
