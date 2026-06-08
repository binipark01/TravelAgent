import type { AgentRunResponse } from '../types/agent'

export const SCOPE_LABELS: Record<string, string> = {
  flight: '항공권',
  accommodation: '숙소',
  restaurant: '식당',
  route: '일정',
  budget: '예산',
}

export const RUN_STATUS_LABELS: Record<string, string> = {
  queued: '대기 중',
  running: '실행 중',
  waiting_for_user: '추가 정보 필요',
  completed: '완료',
  failed: '실패',
}

/** core_plan_decided 이벤트에서 코어가 고른 서브에이전트 키 목록을 꺼낸다. */
export function coreSelectedAgents(data: AgentRunResponse): string[] {
  const event = data.events.find((item) => item.type === 'core_plan_decided')
  const agents = event?.payload?.agents
  return Array.isArray(agents) ? agents.map(String) : []
}

/** /agent/runs 응답을 대화 말풍선용 자연어 답변으로 요약한다. (mock 데이터는 제외) */
export function buildAgentRunAnswer(data: AgentRunResponse): string {
  if (data.status === 'failed') {
    return '요청을 처리하다 문제가 생겼어요. 잠시 후 다시 시도해 주세요.'
  }

  const plan = data.partial_plan
  const summary = data.state_summary
  const destination = summary?.destination ?? plan?.selected_destination ?? '목적지'

  const realFlights = (plan?.transport_options ?? []).filter((option) => !option.metadata.is_mock)
  const realHotels = (plan?.accommodation_options ?? []).filter(
    (option) => !option.metadata.source_ref.is_mock,
  )
  const realPois = (plan?.poi_candidates ?? []).filter(
    (option) => !option.metadata.source_ref.is_mock,
  )
  const budget = plan?.budget ?? null

  const lines: string[] = [`${destination} 실시간 검색 결과예요.`]

  if (realFlights.length) {
    lines.push(summarizeFlights(realFlights))
  }
  if (realHotels.length) {
    lines.push(summarizeHotels(realHotels))
  }
  if (realPois.length) {
    lines.push(`🍴 맛집 ${realPois.length}곳을 평점순으로 추렸어요. (구글 지도)`)
  }
  if (budget) {
    const total = Math.round(budget.total_estimated_cost).toLocaleString('ko-KR')
    const per = Math.round(budget.per_person_estimated_cost).toLocaleString('ko-KR')
    lines.push(`💰 예상 총비용 약 ₩${total} (1인 ₩${per})`)
  }

  if (lines.length > 1) {
    return lines.join('\n')
  }
  return `${destination} 실시간 결과를 가져오지 못했어요. (mock 데이터는 표시하지 않습니다)`
}

/** 검색한 날짜 범위와 최저가 추천을 한 줄로 정리한다. */
function summarizeFlights(flights: AgentRunResponse['partial_plan']['transport_options']): string {
  const dates = [...new Set(flights.map((option) => option.departure_time.slice(0, 10)))].sort()
  const prices = flights.map((option) => option.price.amount).filter((amount) => amount > 0)
  const dateSpan =
    dates.length > 1 ? `${shortDate(dates[0])}~${shortDate(dates[dates.length - 1])} 여러 날짜` : shortDate(dates[0])

  if (!prices.length) {
    return `✈️ ${dateSpan}를 검색해 항공 ${flights.length}개를 추렸어요.`
  }
  const min = Math.min(...prices)
  const best = flights.find((option) => option.price.amount === min)
  const bestDate = best ? shortDate(best.departure_time.slice(0, 10)) : ''
  const bestAirline = best ? cleanAirline(best.airline) : ''
  return (
    `✈️ ${dateSpan}를 검색해 항공 ${flights.length}개를 추렸어요. ` +
    `최저가는 ${min.toLocaleString('ko-KR')}원(${bestAirline}, ${bestDate} 출발)이에요.`
  )
}

/** 숙소 개수와 1박 최저가를 한 줄로 정리한다. */
function summarizeHotels(hotels: AgentRunResponse['partial_plan']['accommodation_options']): string {
  const prices = hotels.map((option) => option.nightly_price.amount).filter((amount) => amount > 0)
  if (!prices.length) {
    return `🏨 숙소 ${hotels.length}곳을 찾았어요.`
  }
  const min = Math.min(...prices)
  return `🏨 숙소 ${hotels.length}곳을 찾았어요. 1박 최저 ₩${min.toLocaleString('ko-KR')}.`
}

function shortDate(iso: string): string {
  const [, month, day] = iso.split('-')
  return month && day ? `${Number(month)}/${Number(day)}` : iso
}

function cleanAirline(airline: string): string {
  return /\bmock\b/i.test(airline) ? '항공' : airline
}
