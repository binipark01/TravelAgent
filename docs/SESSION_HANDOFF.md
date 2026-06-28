# 세션 핸드오프 — 일정 품질·지도·intake·트리플 데이터 연동

이 세션(커밋 `95f8541`~`ced42e7`, 16개)에서 한 일을 Codex가 숙지하도록 정리한다.
주제: ① 일정 스케줄 품질(결정적 규칙) ② 지도/지오코딩 정확도 ③ intake·목적지 해석 ④ 내용
카드 robustness ⑤ **트리플 실코스 4.7만건 데이터셋 연동**. 모든 변경은 ruff clean + pytest
전체 통과(현재 309) + 골든(`tests/test_workflow_step_order.py`) 단계순서 불변을 유지.

## 0. 작업 방식(이 프로젝트의 불변 규칙)
- 구현 → `ruff check` + `pytest -p no:cacheprovider` → 파이썬 변경이면 서버 재시작
  (`./stop_servers.ps1; ./start_servers.ps1`) → **라이브 검증**(아래 프로브/스크립트) → 커밋·푸시.
- 실제 작업 체크아웃은 메인 `D:\Agents\TravelAgent`(이 worktree 디렉터리는 빔).
- 추천/판단은 **하드코딩 점수기 금지, LLM 웹검색 종합 우선**. 단 이름→좌표/통화코드 같은
  '결정' 폴백은 LLM 리졸버 사용 OK.
- LLM은 `live_llm_local_enabled`/`live_llm_web_enabled`로 게이팅. 오프라인(테스트)은 휴리스틱
  폴백 경로만 탄다.

## 1. 일정 스케줄 — 결정적 규칙 (route_optimizer.py + critic.py + itinerary_arranger.py)
사용자 분노 포인트("1시까지 가는 일정", "깜깜할 때 경치", "밤에 어시장")를 결정적으로 차단.
- **22시 캡**(`_past_day_cap`, `_DAY_END_CAP=22:00`): 비-야경·비-anchor 관광은 22시 전 종료.
  자정 wrap(`_add_minutes`가 25:00→01:00) 도 '초과'로 처리.
- **귀가 도착 캡**(`_past_home_cap`, `_HOME_RETURN_CAP=23:00`): 관광이 22시 전 끝나도 먼 근교
  귀가 이동이 자정으로 밀리는 걸 차단(사도·후라노/비에이). `return_leg`(마지막 정류장→숙소)로
  '귀가 도착 시각' 투영. 첫 관광은 안 자름(최소 1곳). 오버랜드 1박 이동일(첫 숙소≠마지막
  숙소)은 제외.
- **야경 예외 키워드**(`_NIGHT_VIEW_KEYWORDS`): 야경/전망/나이트/일몰/루프톱 등만 22시 넘김
  허용. **'바'·'bar' 같은 짧은 토큰 금지**(부분일치로 '바트요/Barcelona/Barri'까지 야경 오분류
  → 캡 누수). 추가 시 부분일치 부작용 주의.
- **일출·일몰 반영**(`open_meteo.fetch_trip_daylight`): 야외 경치=일몰 전, 야경=일몰 후.
  arranger `_daylight_block`. 가까운 날짜는 Open-Meteo, 먼 날짜는 NOAA 로컬계산 폴백.
- **업종 영업시간**(arranger `_business_hours_block` + critic `_business_hours_flags`): 시장류
  오전, 박물관 17:30 이전 마감, 야시장·바 저녁. 특정 POI 시간 날조 금지(업종 상식만).
- **과밀 판정**(critic): anchor(공항·숙소) 제외 실관광 6곳+만 과밀(북엔드 2개 때문에 매일 뜨던
  노이즈 제거).
- **먼 근교 당일치기 판단**(critic `_daytrip_feasibility_flags`): 편도 90분+ & 그날 총 이동 5h+면
  "당일치기 빠듯, 1박 고려" 플래그. 1박 이동일은 제외.
- **먼 근교 증거 기반**(arranger 프롬프트): 당일치기/현지 1박 결정을 후기(웹검색)에 근거. 근거
  없는 먼 당일치기 금지(빼거나 1박).
- **공항 북엔드**: day1 첫 stop=도착공항, 마지막날 마지막=출국공항. 숙소 출발·복귀.

## 2. 지도 / 지오코딩 정확도
- **프론트 체인**: `ItineraryItem.location.latitude/longitude` → DayPlanCard가 place.lat/lng로
  넘김 → MapCard가 좌표면 **지오코딩 없이** 바로 찍음. 좌표 없으면 이름 지오코딩(+bounds bias).
- **멀티지역 anchor 버그**(PlanCards `excursionAnchor`): area가 '·'로 이은 멀티지역이면 연결
  문자열 대신 국가(tickets.destination_country, 폴백 hub)로 anchor — 안 그러면 모든 stop이 첫
  토큰(비슈케크)으로 붕괴.
- **geocode 폴백**(open_meteo.geocode): 한글 도시명이 Open-Meteo에 없으면(암스테르담·비엔나)
  geo_resolver의 영문명·좌표로 폴백(지연 import). 날씨·일몰·교통권 hub좌표 동시 복구.
- **★ 근본 해결(트리플)**: §5 참조 — 63도시는 실좌표가 POI에 박혀 지오코딩 자체가 사라짐.

## 3. intake / 목적지 해석 (agents/llm_client.py, agents/intake.py, agents/destination.py)
- **selected_destination = 단일 허브 도시 강제**: 국가('이탈리아')·연결('A + B','A·B')·지역
  ('일본 온천 지역') 금지. 멀티시티면 거점 1도시 + 나머지는 destinations[], 근교·랜드마크
  (그랜드캐니언·하롱베이)는 must_include. 모든 지명 한글.
- **접근성·식이 필드**: 휠체어/배리어프리→accessibility_needs, 비건/할랄→dietary_restrictions
  (must_include에만 넣지 말 것). 예산 '1인당 N'→budget_per_person만.
- **모호 목적지 → LLM 추천**(curator `recommend_destinations`): '일본 온천'→유후·벳푸, '따뜻한
  휴양'→다낭·세부, '유럽'→프라하·부다페스트. destination_agent가 목적지 비었거나 국가·지역뿐일
  때 hint로 추천 → 거점 확정. 하드코딩 'Osaka' 폴백 제거. LLM off면 최후 기본 도시(오사카).
- **명시 멀티시티**(route_optimizer `_course_companion_days`): brief.destinations 2도시+면 거점
  뺀 도시에 일수 분배(로마4·피렌체2·베네치아2) → curate_community_course에 companion_days로
  전달 → 일정이 도시를 걸쳐 돈다(거점이 첫날·마지막날). community-course/arrange 둘 다 지원.

## 4. 내용 카드 robustness (connectors/, curator)
- **현지교통 LLM 폴백**(curator `curate_local_transport`): 정적 데이터가 아시아 10도시뿐이라
  서구권 누락 → 웹검색 폴백(공항이동·교통패스, 특정 출발시각 날조 X).
- **환율 통화**(connectors/fx/exchange_rate): 유로존 개별국 + 비유로존 유럽(스위스 CHF·체코
  CZK 등) + 롱테일은 geo_resolver `currency`(ISO 4217) LLM 폴백(키르기스 KGS). er-api.com이
  통화 지원, 메타 없으면 generic 메타.
- **큐레이터 transient 재시도**(curator `_run`): run_codex_json이 타임아웃·빈응답에 None →
  1회 재시도. 정상 빈결과(dict)는 재시도 안 함(대기 2배 방지).
- geo_resolver 확장: `city_en`, `lat/lng`, `currency` 필드 추가(프롬프트·파싱).

## 5. ★ 트리플 실코스 데이터셋 연동 (connectors/course_store/triple_store.py)
- 원본 `.omo/triple-all-cases/.../schedule_cases.jsonl`(592MB, 47628건, triple.guide 스크랩).
  63도시 × (기간6×동행7×스타일9×피로도2=756) 격자. 891k POI에 **실좌표·평점·카테고리** 보유.
- `scripts/build_triple_store.py`: 도시별 컴팩트 JSON(`.omo/triple-store/`, 29MB)으로 1회 distill.
- 런타임 `triple_store.lookup_poi(도시,POI명)`·`lookup_course(도시,일수,interests/who/pace)`,
  지연로드·캐시, 스토어 없으면 None(graceful → 웹검색 폴백). period=nights+1.
- **#1 좌표**: route_optimizer `_arranged_item`이 트리플 좌표를 Location에 주입(additive) →
  지도 오매칭 원천 차단. 어느 코스 소스든 적용.
- **#2 코스**: 단일도시·1~6일·63도시면 `_arrangement_from_store`가 community-course **앞에서**
  ArrangedItinerary로 변환(좌표 haversine→이동시간, 카테고리→체류시간). 즉시·결정적.
- **주의**: `.omo`는 git 비추적 — 환경마다 build_triple_store.py 실행 필요. 테스트는 conftest가
  빈 TRIPLE_STORE_DIR로 비활성(기존 fallback 보존).

## 6. 검증 도구 (scripts/, 모두 .omo/scratchpad에 결과)
- `sweep_cities_light.py`: route_agent만 돌려 일정 차원(캡·일몰·시장·박물관·북엔드) 도시당 ~1콜.
- `sweep_full_verify.py`: `run_agent_workflow`(실제 앱 경로)로 비자·환율·항공·hub좌표·POI·근교·
  숙박·교통·예산·체크리스트까지 **모든 카드 내용**을 도시별 기대값과 대조.
- `multicity_quality_probe.py`, `nl_intake_probe.py`, `nl_multicity_probe.py`: 자연어 질의 파싱·
  멀티시티·국내 검증. **도시 검증은 항상 `run_agent_workflow`로**(run_planning은 stay_area·
  checklist·events·multicity 빠진 축약 경로).

## 7. 25개 메인도시 전수 검증 결과 (이 세션)
유럽10·아시아10·미국5 전체 파이프라인 검증 → 일정 25/25 정상(공항 북엔드·비-야경 자정 0),
발견·수정: 먼근교 자정·바/bar 캡누수·현지교통 누락·취리히 통화·암스테르담 hub좌표·멀티지역
지오코딩·모호목적지 Osaka·멀티시티 단일도시 머무름·키르기스 KGS. 키르기스(비슈케크)도 통과.

## 8. 알려진 한계 / 후속 후보
- 항공 스크래퍼 가끔 0건(다낭 1건) — 큐레이터 아닌 별도 경로, transient 재시도 미적용.
- 트리플 스토어: 63도시·1~6일·단일도시만(제주·비슈케크·7일+·멀티시티는 웹검색). 멀티시티를
  도시별 스토어 조회로 이어붙이는 건 미구현.
- 트리플 코스의 공항→시내 이동시간이 haversine 기반이라 먼 공항(나리타)에서 과대추정 경향.
- 국내(제주)는 비자/환율/국제항공 카드가 무의미 — 생략 처리 미검증.
