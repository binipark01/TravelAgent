---
name: llm-prompt-tuning
description: "TravelAgent의 LLM 큐레이터·일정 배치기 프롬프트(curator.py·itinerary_arranger.py)를 손볼 때 사용. 추천 품질·일정 동선·곳수·시간대·공항/숙소 anchor 등 '일정이 이상해/추천이 별로야/동선이 이상해/너무 과밀해/야경을 아침에' 류 품질 이슈, 프롬프트 규칙 추가·조정 요청 시 반드시 사용."
---

# LLM Prompt Tuning — 큐레이터·배치기 프롬프트

이 프로젝트의 차별점은 LLM 프롬프트 품질이다. 코드 점수기 대신 LLM 웹검색 종합으로 추천하고, 일정 동선도 LLM이 짠다. 프롬프트는 데이터처럼 다룬다.

## 어디를 만지나
- `app/llm/curator.py` — 관광지·식당·근교·숙박구역·이벤트·동반도시 큐레이션(웹검색). 인기도 우선, niche 패딩 금지, 한국어명(원어 병기).
- `app/llm/itinerary_arranger.py`
  - `arrange_itinerary` — 풀 기반 일정 배치(웹검색 없음, 폴백 경로).
  - `curate_community_course` — 디시·네이버카페·블로그 실후기 코스(웹검색, **1순위 경로**).
  - 두 프롬프트는 규칙을 **양쪽에 똑같이** 넣어야 한다(경로가 갈리므로 한쪽만 고치면 다른 플랜에서 누락).

## 검증된 규칙(되돌리지 말 것)
- **시간대 적합성** — 야경·전망대=저녁/마지막, 새벽시장=오전, 실내(미술관)=한낮/비.
- **인기도 우선** — 실제 여행자 많이 가는 곳, 학술 유적·동네 박물관 niche 금지.
- **단일 단지=한 stop** — 베르사유(궁전+정원+트리아농)·테마파크·국립공원은 내부를 쪼개지 말고 한 stop, 내부 이동 동선 만들지 말 것.
- **공항 bookend** — 첫날 첫 stop=도착공항, 마지막날 마지막 stop=출국공항(도시별 정확한 공항: 오사카=간사이). 먼 근교는 마지막날 금지.
- **숙소 bookend** — 첫날·마지막날 뺀 모든 날은 본거지(숙소 부근/역)에서 출발해 본거지로 복귀(왕복).
- **과밀 금지** — 하루 관광 4~5곳(숙소 출발·복귀 stop은 수에서 제외), 현실적 duration(대형 미술관만 150~180분), 마지막 관광 18~19시 종료(자정까지 끌지 말 것).

## 라이브 검증 방법 (오프라인 테스트로는 못 잡음)
프롬프트는 게이트(`enable_live_llm`+web_search) 뒤라 단위 테스트가 안 돈다. LLM을 직접 호출하거나 서버 API로 확인한다:
```bash
# LLM 함수 직접 호출 (Windows: 한자 출력 위해 utf-8)
PYTHONIOENCODING=utf-8 python -c "
from datetime import date
from travel_agent.app.llm.itinerary_arranger import curate_community_course
c = curate_community_course('파리', days_count=5, interests=None, start_date=date(2026,7,1))
for d in c.days: print(d.day, d.area, [s.title for s in d.stops])
"
```
- 캐시(`_COMMUNITY_COURSE_CACHE`)는 프로세스 메모리라 새 프로세스/서버 재시작이면 새 프롬프트로 재질의된다.
- 서버 전체 파이프라인 검증은 `live-verify` 스킬(POST /agent/runs → 폴링).

## 마무리
규칙을 두 프롬프트에 모두 반영했는지 확인하고, 라이브로 1~2개 도시(가능하면 일본+유럽)로 검증한 결과를 첨부한다.
