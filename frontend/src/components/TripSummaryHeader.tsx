import type { TripStateSummary } from '../types/agent'
import { formatNumber } from '../utils/format'

/** 여행 캔버스 상단 요약: 목적지·날짜·인원·총예산·날씨를 한 줄에. */
export function TripSummaryHeader({
  summary,
  weather,
}: {
  summary?: TripStateSummary | null
  weather?: string | null
}) {
  if (!summary) return null
  const route = [summary.origin, summary.destination].filter(Boolean).join(' → ')
  const title = summary.destination || route || '여행 계획'
  const sub = [summary.date_range, summary.travelers ? `${summary.travelers}명` : null]
    .filter(Boolean)
    .join(' · ')

  return (
    <header className="trip-summary">
      <div className="trip-summary__main">
        <h1>{title}</h1>
        {sub && <p className="trip-summary__sub">{sub}</p>}
      </div>
      <div className="trip-summary__stats">
        {summary.budget_total ? (
          <div className="trip-stat">
            <span>총 예상</span>
            <strong>{formatNumber(summary.budget_total, 'KRW')}</strong>
          </div>
        ) : null}
        {weather ? (
          <div className="trip-stat">
            <span>날씨</span>
            <strong>{weather}</strong>
          </div>
        ) : null}
      </div>
    </header>
  )
}
