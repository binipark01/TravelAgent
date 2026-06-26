---
name: live-verify
description: "TravelAgent 변경을 실제로 검증할 때 사용 — 백엔드 응답과 프론트 타입/훅의 경계면 교차 비교, pytest·npm build, 라이브 API 프로브(POST /agent/runs 폴링), 브라우저 동선/화면 확인, 지오코딩 좌표 확인. '검증해줘/확인해줘/진짜 되는지/라이브로 돌려봐/경계면 맞나', QA·회귀 점검 요청 시 반드시 사용."
---

# Live Verify — 통합·라이브 검증

"파일이 있다/렌더된다"가 아니라 "백엔드가 주는 것을 프론트가 정확히 읽고, 실제로 동작한다"를 확인한다. 이 프로젝트 버그는 대부분 경계면에서 났다.

## 1. 구조·단위 검증
```bash
python -m pytest tests/ -p no:cacheprovider -q
python -m ruff check <changed py files>
cd frontend && npm run build
```

## 2. 라이브 API 프로브 (오프라인 테스트가 못 잡는 LLM·통합 경로)
서버 재시작 후 실제 run을 만들어 응답 데이터를 직접 검증한다:
```bash
./stop_servers.ps1; ./start_servers.ps1   # 백엔드 127.0.0.1:8000
```
```python
# Windows 콘솔 한글/한자 깨지면 PYTHONIOENCODING=utf-8 또는 파일로 저장해 Read
import json, time, urllib.request
BASE='http://127.0.0.1:8000/agent/runs'
def post(m):
    r=urllib.request.Request(BASE,data=json.dumps({'message':m}).encode(),headers={'Content-Type':'application/json'})
    return json.loads(urllib.request.urlopen(r,timeout=60).read())
def get(rid): return json.loads(urllib.request.urlopen(f'{BASE}/{rid}',timeout=60).read())
rid=post('오사카 3박4일 여행 일정 짜줘')['run_id']
for _ in range(160):
    time.sleep(2); d=get(rid)
    if (d.get('state') or {}).get('optimized_itinerary'):
        if d['run']['status'] in ('completed','failed','cancelled','waiting_for_user'): break
# d['state']['optimized_itinerary']['days'][k]['items'/'transfers'/'meals'] 를 검증
```

## 3. 경계면 교차 비교 (핵심)
한쪽이 아니라 양쪽을 동시에 읽고 shape을 맞댄다:
- 백엔드 응답 JSON 필드/타입 ↔ `frontend/src/types/`·컴포넌트가 읽는 필드
- 큐레이터/배치기 출력(ArrangedStop 등) ↔ `route_optimizer`가 조립하는 DayPlan 필드
- 새 필드 추가 시: 백엔드가 채우는가 + 프론트가 같은 이름/타입으로 읽는가 + 누락 시 폴백이 있는가

## 4. 브라우저·지오코딩 확인 (필요 시)
- Chrome MCP로 실제 화면/동선 캡처. 동선 보기 버튼은 ref 클릭이 React onClick에 안 걸리면 좌표 클릭으로.
- 지명 우회 의심 시 `google.maps.Geocoder`로 좌표를 직접 찍어 권역 이탈 여부 확인. DirectionsService로 경로 bounds 계산해 우회 검출.

## 5. 보고
PASS/FAIL 표 + 근거(테스트 출력·프로브 데이터·좌표·스크린샷). FAIL이면 **어느 경계면의 어떤 필드가 어긋났는지** 구체적으로. 통과 못 한 것을 통과처럼 보고하지 않는다. 부분 변경이면 회귀부터 본다.
