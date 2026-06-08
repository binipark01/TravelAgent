# TravelAgent

Evidence 기반 multi-agent 해외 여행 planning MVP입니다.

이 프로젝트의 기본 흐름은 `/agent/runs`입니다. 사용자는 자연어 요청을 보내고, `AgentRuntime`이 `TravelSupervisorAgent`, domain sub-agent, source discovery, tool, connector, evidence 저장, critic 검증, presentation 생성을 순서대로 실행합니다.

## 실행

```bash
python -m pip install -e ".[dev]"
python -m uvicorn travel_agent.app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

기본 URL:

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5174`
- Health: `http://127.0.0.1:8000/health`

## 핵심 API

`POST /agent/runs`

```json
{
  "message": "10월 초 일본 4박 5일 여행 가고 싶어",
  "locale": "ko-KR",
  "currency": "KRW",
  "timezone": "Asia/Seoul"
}
```

`GET /agent/runs/{run_id}`는 run, steps, events, state summary, 현재 plan state를 반환합니다.

`POST /agent/runs/{run_id}/messages`는 같은 run에 사용자 답변을 붙이고 대기 중인 run을 재개합니다.

`GET /providers/status`는 source policy 결과를 반환합니다. secret 값은 반환하지 않습니다.

## Agent Runtime

현재 runtime 경로:

1. `AgentRuntime.start_run`
2. `TravelSupervisorAgent`
3. `SourceRegistry` / `SourcePolicy`
4. domain agent workflow
5. `ToolExecutor`
6. connector/provider 결과 normalization
7. `EvidencePacket` 저장
8. `TripPlanState` snapshot
9. `PlanCriticAgent`
10. `PresentationAgent`

Agents는 HTTP API를 직접 호출하지 않아야 합니다. 실제 source 접근은 tool과 connector 계층 뒤에서만 수행합니다.

## Provider와 mock 정책

기본값은 다음과 같습니다.

```env
ENABLE_LIVE_PROVIDERS=false
PROVIDER_FALLBACK_TO_MOCK=true
```

이 상태에서는 mock connector/provider만 사용되며, `SourceRef.is_mock=true`, `EvidencePacket.confidence` 낮음, freshness warning으로 표시됩니다. Live provider를 켜려면 `.env.example`의 source별 credential을 설정해야 합니다. credential이 없고 fallback이 꺼져 있으면 `ProviderConfigurationError`가 발생합니다.

## 금지 사항

- 실제 결제, 발권, 예약, 취소, 이메일 발송, calendar side effect

Booking simulation은 반드시 approval gate를 통과해야 하며 실제 booking을 만들지 않습니다.

## 테스트

```bash
ruff check . --no-cache
python -m pytest -p no:cacheprovider
```

```bash
cd frontend
npm run lint
npm run test
npm run build
```

## 새 connector 추가

1. `travel_agent/app/sources/source_catalog.yaml`에 source를 추가합니다.
2. `SourcePolicy`에서 허용 가능한 source type인지 확인합니다.
3. `travel_agent/app/connectors/{domain}`에 connector를 추가합니다.
4. connector output을 normalizer/tool에서 `EvidencePacket`으로 변환합니다.
5. live network 없는 mocked HTTP test를 추가합니다.
