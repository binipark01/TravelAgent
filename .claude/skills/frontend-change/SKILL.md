---
name: frontend-change
description: "TravelAgent 프론트(React 19 + Vite + TS) 컴포넌트·훅·타입·지도/일정 UI를 추가·수정·디버그할 때 사용. PlanCards·MapCard·DayPlanCard·HomePage 변경, 레이아웃·동선·폴링·렌더 버그, '화면 고쳐줘/UI 바꿔줘/지도가 이상해/안 떠/2열로/무한루프', '다시/보완' 요청 시 반드시 사용."
---

# Frontend Change — TravelAgent React 변경 절차

## 구조
- `frontend/src/pages/HomePage.tsx` — 턴 관리 + TanStack Query 폴링(~1.2s)으로 부분 결과 점진 렌더.
- `frontend/src/components/` — `PlanCards`(카드 오케스트레이션 + MapFocus provider), `MapCard`(Google Maps JS / 임베드 폴백), `DayPlanCard`/`ItineraryTimeline`(일정), 각 결과 카드.
- `frontend/src/types/` — 백엔드 응답과 매칭되는 TS 타입.

## 검증된 함정(되풀이 금지)
- **무한 렌더** — `useQuery` 반환 객체는 매 렌더 새 참조. `useEffect` deps에 `runsQuery` 통째로 넣으면 setState→리렌더→effect 무한반복("Maximum update depth exceeded")으로 지도 타일까지 안 그려진다. `refetch` 등 안정 참조만 꺼내 쓴다.
- **지도 동선 mode** — 경유지 있는 경로는 `DRIVING`. TRANSIT은 waypoints 미지원→INVALID_REQUEST→WALKING 폴백 시 간사이공항 같은 인공섬을 100km 우회한다.
- **동선 anchor** — 본거지(숙소)에서 출발해 본거지로 닫는다. 본거지는 그날 region이 아니라 도시(hub)로 지오코딩, 괄호·`·`·`/`는 떼고 깔끔한 대표명만. 첫 stop이 공항이면(도착일) 그대로.
- **HMR vs 탭** — 코드 저장은 dev 서버에 즉시 반영되지만 열려있던 브라우저 탭은 새로고침해야 보인다.

## 작업 원칙
- **타입 정합성** — 백엔드 응답 shape이 바뀌면 `types/`부터 맞춘다. shape 불명확하면 backend-engineer에 확인.
- **2열 레이아웃** — 일정/후보 카드는 번갈아 2열(짧은 카드 빈공간 방지). 좁은 화면 1열.
- 주석은 한국어 관례 유지.

## 검증 (필수)
```bash
cd frontend && npm run build    # tsc -b && vite build, 반드시 통과
```
시각/동선 확인은 qa-verifier의 `live-verify`(브라우저)로.

## 마무리
변경 파일·diff 요약·빌드 결과 보고. 백엔드에 기대하는 응답 shape이 있으면 명시.
